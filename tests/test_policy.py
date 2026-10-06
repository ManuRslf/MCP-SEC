import os
from pathlib import Path

import pytest

from gateway import policy


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    directories = {name: tmp_path / name for name in ("public", "output", "secrets")}
    for directory in directories.values():
        directory.mkdir()
    (directories["public"] / "document.txt").write_text("Public document")
    (directories["secrets"] / "password.txt").write_text("Dummy test secret")
    monkeypatch.setattr(policy, "ALLOWED_ROOTS", {
        "read_file": directories["public"],
        "list_directory": directories["public"],
        "write_file": directories["output"],
    })
    return directories


def request(tool, path, **extra):
    arguments = {"path": str(path)}
    if tool == "write_file":
        arguments["content"] = "Summary"
    arguments.update(extra)
    return policy.authorize(tool, arguments)


@pytest.mark.parametrize("tool,folder,name", [
    ("read_file", "public", "document.txt"),
    ("list_directory", "public", ""),
    ("write_file", "output", "summary.txt"),
])
def test_valid_requests_return_resolved_path(sandbox, tool, folder, name):
    path = sandbox[folder] / name
    decision = request(tool, path)
    assert decision.allowed
    assert decision.resolved_path == path.resolve()


def test_write_can_overwrite_a_regular_file_with_empty_content(sandbox):
    destination = sandbox["output"] / "existing.txt"
    destination.write_text("Original")
    decision = request("write_file", destination, content="")
    assert decision.allowed
    assert destination.read_text() == "Original"


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
@pytest.mark.parametrize("escape", ["direct", "traversal", "symlink", "prefix"])
def test_paths_outside_allowed_root_are_denied(sandbox, tool, escape):
    root = sandbox["output" if tool == "write_file" else "public"]
    target = sandbox["secrets"]
    if tool != "list_directory":
        target /= "password.txt"
    if escape == "direct":
        path = target
    elif escape == "traversal":
        path = root / ".." / "secrets" / target.relative_to(sandbox["secrets"])
    elif escape == "symlink":
        path = root / "escape"
        path.symlink_to(target, target_is_directory=tool == "list_directory")
    else:
        sibling = root.with_name(root.name + "_backup")
        sibling.mkdir()
        path = sibling
        if tool != "list_directory":
            path /= "document.txt"
            path.write_text("Outside allowed root")
    assert not request(tool, path).allowed


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
def test_nested_paths_inside_allowed_root_are_allowed(sandbox, tool):
    root = sandbox["output" if tool == "write_file" else "public"]
    nested = root / "nested"
    nested.mkdir()
    path = nested
    if tool != "list_directory":
        path /= "document.txt"
        if tool == "read_file":
            path.write_text("Nested document")
    assert request(tool, path).allowed


@pytest.mark.parametrize("tool", ["delete_file", "", None, [], {}])
def test_unknown_or_invalid_tools_are_denied(tool):
    assert not policy.authorize(tool, {"path": "/unused"}).allowed


@pytest.mark.parametrize("arguments", [None, [], ["path"], "path", 1, {}])
def test_invalid_argument_containers_are_denied(arguments):
    assert not policy.authorize("read_file", arguments).allowed


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
def test_unexpected_arguments_are_denied(sandbox, tool):
    root = sandbox["output" if tool == "write_file" else "public"]
    assert not request(tool, root, unexpected=True).allowed


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
def test_missing_path_is_denied(tool):
    arguments = {"content": "Summary"} if tool == "write_file" else {}
    assert not policy.authorize(tool, arguments).allowed


@pytest.mark.parametrize("path", [None, 123, [], "", "   ", "relative.txt"])
@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
def test_invalid_paths_are_denied(tool, path):
    arguments = {"path": path}
    if tool == "write_file":
        arguments["content"] = "Summary"
    assert not policy.authorize(tool, arguments).allowed


def test_missing_write_content_is_denied(sandbox):
    arguments = {"path": str(sandbox["output"] / "summary.txt")}
    assert not policy.authorize("write_file", arguments).allowed


@pytest.mark.parametrize("content", [None, 123, [], {}])
def test_non_string_write_content_is_denied(sandbox, content):
    assert not request("write_file", sandbox["output"] / "summary.txt", content=content).allowed


@pytest.mark.parametrize("tool", ["read_file", "list_directory"])
def test_missing_targets_are_denied(sandbox, tool):
    assert not request(tool, sandbox["public"] / "missing").allowed


def test_reading_directory_is_denied(sandbox):
    assert not request("read_file", sandbox["public"]).allowed


def test_listing_file_is_denied(sandbox):
    assert not request("list_directory", sandbox["public"] / "document.txt").allowed


def test_writing_directory_is_denied(sandbox):
    assert not request("write_file", sandbox["output"]).allowed


def test_write_with_missing_parent_is_denied(sandbox):
    assert not request("write_file", sandbox["output"] / "missing" / "summary.txt").allowed


def test_write_with_file_as_parent_is_denied(sandbox):
    parent = sandbox["output"] / "existing.txt"
    parent.write_text("Existing file")
    assert not request("write_file", parent / "summary.txt").allowed


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Named pipes are unavailable")
def test_writing_special_file_is_denied(sandbox):
    pipe = sandbox["output"] / "pipe"
    os.mkfifo(pipe)
    assert not request("write_file", pipe).allowed


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
def test_null_character_path_is_denied(sandbox, tool):
    root = sandbox["output" if tool == "write_file" else "public"]
    assert not request(tool, str(root / "invalid") + "\0").allowed


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
def test_symlink_loop_is_denied(sandbox, tool):
    root = sandbox["output" if tool == "write_file" else "public"]
    link = root / "loop"
    link.symlink_to(link)
    assert not request(tool, link).allowed


def test_dangling_write_symlink_outside_output_is_denied(sandbox):
    link = sandbox["output"] / "escape"
    link.symlink_to(sandbox["secrets"] / "new.txt")
    assert not request("write_file", link).allowed


def test_write_through_symlinked_parent_outside_output_is_denied(sandbox):
    link = sandbox["output"] / "escape"
    link.symlink_to(sandbox["secrets"], target_is_directory=True)
    assert not request("write_file", link / "new.txt").allowed


def test_allowed_symlink_returns_destination(sandbox):
    target = sandbox["public"] / "document.txt"
    link = sandbox["public"] / "alias.txt"
    link.symlink_to(target)
    decision = request("read_file", link)
    assert decision.allowed
    assert decision.resolved_path == target


@pytest.mark.parametrize("error", [PermissionError, OSError, ValueError, RuntimeError])
def test_resolution_errors_return_denied_decisions(sandbox, monkeypatch, error):
    def fail_resolution(self, **kwargs):
        raise error("Simulated filesystem failure")

    monkeypatch.setattr(Path, "resolve", fail_resolution)
    assert not request("read_file", sandbox["public"] / "document.txt").allowed


def test_filesystem_inspection_error_returns_denied_decision(sandbox, monkeypatch):
    def fail_inspection(self):
        raise PermissionError("Simulated filesystem failure")

    monkeypatch.setattr(Path, "is_file", fail_inspection)
    assert not request("read_file", sandbox["public"] / "document.txt").allowed
