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
