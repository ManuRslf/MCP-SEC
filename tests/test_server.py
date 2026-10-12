import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_server import server


@pytest.fixture
def server_sandbox(sandbox, monkeypatch):
    monkeypatch.setattr(server, "SANDBOX_ROOT", sandbox["public"].parent)
    return sandbox


@pytest.fixture
def outside(tmp_path_factory):
    directory = tmp_path_factory.mktemp("outside-server-sandbox")
    (directory / "document.txt").write_text("Outside document", encoding="utf-8")
    return directory


def call_tool(tool, path):
    function = getattr(server, tool)
    if tool == "write_file":
        return function(str(path), "Replacement text")
    return function(str(path))


def test_read_returns_utf8_text_unchanged(server_sandbox):
    path = server_sandbox["public"] / "unicode.txt"
    content = "Caf\u00e9\n\u65e5\u672c\u8a9e\n"
    path.write_text(content, encoding="utf-8")

    assert server.read_file(str(path)) == content


def test_server_can_read_dummy_secret_inside_sandbox(server_sandbox):
    path = server_sandbox["secrets"] / "password.txt"

    # Per-tool public/output restrictions belong to the gateway.
    assert server.read_file(str(path)) == "Dummy test secret"


@pytest.mark.parametrize("content", ["Summary", "", " \n\t ", "Caf\u00e9\n\u65e5\u672c\u8a9e"])
@pytest.mark.parametrize("existing", [False, True])
def test_write_creates_or_overwrites_utf8_files(server_sandbox, content, existing):
    path = server_sandbox["output"] / "summary.txt"
    if existing:
        path.write_text("Original longer content", encoding="utf-8")

    result = server.write_file(str(path), content)

    assert isinstance(result, str)
    assert result
    assert path.read_bytes() == content.encode("utf-8")


@pytest.mark.parametrize("content", [None, 123, b"bytes", {}])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_content_type_does_not_modify_files(server_sandbox, content, existing):
    path = server_sandbox["output"] / "summary.txt"
    if existing:
        path.write_text("Original content", encoding="utf-8")

    with pytest.raises(TypeError, match="must be a string"):
        server.write_file(str(path), content)

    if existing:
        assert path.read_text(encoding="utf-8") == "Original content"
    else:
        assert not path.exists()


@pytest.mark.parametrize("content", ["\ud800", "Valid prefix\udfff"])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_utf8_does_not_create_or_truncate_files(server_sandbox, content, existing):
    path = server_sandbox["output"] / "summary.txt"
    if existing:
        path.write_text("Original content", encoding="utf-8")

    with pytest.raises(ValueError, match="valid UTF-8"):
        server.write_file(str(path), content)

    if existing:
        assert path.read_text(encoding="utf-8") == "Original content"
    else:
        assert not path.exists()


def test_listing_returns_sorted_immediate_entry_names(server_sandbox):
    directory = server_sandbox["output"]
    (directory / "z.txt").write_text("Last")
    (directory / "a-folder").mkdir()
    (directory / "a-folder" / "nested.txt").write_text("Nested")
    (directory / "m.txt").write_text("Middle")

    assert server.list_directory(str(directory)) == ["a-folder", "m.txt", "z.txt"]


def test_listing_empty_directory_returns_empty_list(server_sandbox):
    assert server.list_directory(str(server_sandbox["output"])) == []


def test_listing_sandbox_root_is_allowed(server_sandbox):
    root = server_sandbox["public"].parent

    assert server.list_directory(str(root)) == ["output", "public", "secrets"]


@pytest.mark.parametrize("tool", ["read_file", "write_file", "list_directory"])
def test_relative_paths_are_rejected(server_sandbox, tool):
    with pytest.raises(ValueError, match="absolute path"):
        call_tool(tool, "relative.txt")


@pytest.mark.parametrize("tool", ["read_file", "write_file", "list_directory"])
@pytest.mark.parametrize("escape", ["direct", "traversal", "symlink", "prefix"])
def test_outside_paths_are_rejected(server_sandbox, outside, tool, escape):
    root = server_sandbox["public"].parent
    target = outside if tool == "list_directory" else outside / "document.txt"
    if escape == "direct":
        path = target
    elif escape == "traversal":
        path = root / os.path.relpath(target, root)
    elif escape == "symlink":
        path = server_sandbox["public"] / "escape"
        path.symlink_to(target, target_is_directory=tool == "list_directory")
    else:
        sibling = root.with_name(root.name + "_backup")
        sibling.mkdir()
        path = sibling
        if tool != "list_directory":
            path /= "document.txt"
            path.write_text("Sibling document", encoding="utf-8")

    with pytest.raises(PermissionError, match="outside the sandbox"):
        call_tool(tool, path)

    assert (outside / "document.txt").read_text(encoding="utf-8") == "Outside document"
    if escape == "prefix" and tool == "write_file":
        assert path.read_text(encoding="utf-8") == "Sibling document"


@pytest.mark.parametrize("tool", ["read_file", "list_directory"])
def test_missing_read_or_listing_target_is_rejected(server_sandbox, tool):
    with pytest.raises(FileNotFoundError):
        call_tool(tool, server_sandbox["public"] / "missing")


def test_reading_directory_is_rejected(server_sandbox):
    with pytest.raises(ValueError, match="regular file"):
        server.read_file(str(server_sandbox["public"]))


def test_listing_file_is_rejected(server_sandbox):
    with pytest.raises(ValueError, match="directory"):
        server.list_directory(str(server_sandbox["public"] / "document.txt"))


def test_writing_directory_is_rejected(server_sandbox):
    with pytest.raises(ValueError, match="regular file"):
        server.write_file(str(server_sandbox["output"]), "Summary")


def test_missing_write_parent_is_not_created(server_sandbox):
    parent = server_sandbox["output"] / "missing"

    with pytest.raises(ValueError, match="existing directory"):
        server.write_file(str(parent / "summary.txt"), "Summary")

    assert not parent.exists()


def test_write_parent_cannot_be_a_file(server_sandbox):
    parent = server_sandbox["output"] / "existing.txt"
    parent.write_text("Original content", encoding="utf-8")

    with pytest.raises(ValueError, match="existing directory"):
        server.write_file(str(parent / "summary.txt"), "Summary")

    assert parent.read_text(encoding="utf-8") == "Original content"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Named pipes are unavailable")
@pytest.mark.parametrize("tool", ["read_file", "write_file"])
def test_special_files_are_rejected(server_sandbox, tool):
    path = server_sandbox["output"] / "pipe"
    os.mkfifo(path)

    with pytest.raises(ValueError, match="regular file"):
        call_tool(tool, path)


@pytest.mark.parametrize("tool", ["read_file", "write_file", "list_directory"])
def test_null_character_paths_are_rejected(server_sandbox, tool):
    with pytest.raises(ValueError):
        call_tool(tool, str(server_sandbox["output"] / "invalid") + "\0")


@pytest.mark.parametrize("tool", ["read_file", "write_file", "list_directory"])
def test_symlink_loops_are_rejected(server_sandbox, tool):
    link = server_sandbox["public"] / "loop"
    link.symlink_to(link)

    with pytest.raises((OSError, RuntimeError)):
        call_tool(tool, link)


def test_dangling_write_symlink_outside_sandbox_is_rejected(server_sandbox, outside):
    target = outside / "new.txt"
    link = server_sandbox["output"] / "escape"
    link.symlink_to(target)

    with pytest.raises(PermissionError, match="outside the sandbox"):
        server.write_file(str(link), "Summary")

    assert not target.exists()


def test_write_through_outside_symlinked_parent_is_rejected(server_sandbox, outside):
    link = server_sandbox["output"] / "escape"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PermissionError, match="outside the sandbox"):
        server.write_file(str(link / "new.txt"), "Summary")

    assert not (outside / "new.txt").exists()


def test_symlinks_inside_sandbox_work(server_sandbox):
    document = server_sandbox["public"] / "document.txt"
    file_link = server_sandbox["output"] / "alias.txt"
    file_link.symlink_to(document)
    directory_link = server_sandbox["output"] / "alias-directory"
    directory_link.symlink_to(server_sandbox["public"], target_is_directory=True)

    assert server.read_file(str(file_link)) == "Public document"
    assert server.list_directory(str(directory_link)) == ["document.txt"]
    server.write_file(str(file_link), "Replacement")
    assert document.read_text(encoding="utf-8") == "Replacement"


@pytest.mark.asyncio
async def test_stdio_tool_discovery_and_execution(server_sandbox):
    root = server_sandbox["public"].parent
    project_root = Path(__file__).resolve().parents[1]
    # Set the child process's sandbox before starting the real MCP server.
    startup = "\n".join([
        "import sys",
        "from pathlib import Path",
        "from mcp_server import server",
        "server.SANDBOX_ROOT = Path(sys.argv[1]).resolve()",
        "server.mcp.run(transport='stdio')",
    ])
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-B", "-c", startup, str(root)],
        cwd=str(project_root),
    )

    async with asyncio.timeout(20):
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=10) as session:
                await session.initialize()
                discovered = await session.list_tools()
                tools = {tool.name: tool for tool in discovered.tools}
                assert set(tools) == {"read_file", "write_file", "list_directory"}
                for name, tool in tools.items():
                    required = {"path", "content"} if name == "write_file" else {"path"}
                    assert set(tool.input_schema["required"]) == required
                    for field in required:
                        assert tool.input_schema["properties"][field]["type"] == "string"

                read_result = await session.call_tool("read_file", {
                    "path": str(server_sandbox["public"] / "document.txt"),
                })
                assert not read_result.is_error
                assert read_result.structured_content == {"result": "Public document"}

                destination = server_sandbox["output"] / "summary.txt"
                payload = "Caf\u00e9\nSummary"
                write_result = await session.call_tool("write_file", {
                    "path": str(destination),
                    "content": payload,
                })
                assert not write_result.is_error
                assert isinstance(write_result.structured_content["result"], str)
                assert destination.read_text(encoding="utf-8") == payload

                listing_result = await session.call_tool("list_directory", {
                    "path": str(server_sandbox["output"]),
                })
                assert not listing_result.is_error
                assert listing_result.structured_content == {"result": ["summary.txt"]}

                invalid_result = await session.call_tool("write_file", {
                    "path": str(destination),
                    "content": 123,
                })
                assert invalid_result.is_error
                assert destination.read_text(encoding="utf-8") == payload
