from pathlib import Path

from mcp.server.mcpserver import MCPServer


SANDBOX_ROOT = (
    Path(__file__).resolve().parents[1] / "sandbox"
).resolve()

mcp = MCPServer("MCP Security Experiment")


@mcp.tool()
def read_file(path: str) -> str:
    """Read a UTF-8 text file inside the experiment sandbox."""
    target = Path(path)

    if not target.is_absolute():
        raise ValueError("rf: An absolute path is required.")

    target = target.resolve(strict=True)

    if not target.is_relative_to(SANDBOX_ROOT):
        raise PermissionError("rf: Path is outside the sandbox.")

    if not target.is_file():
        raise ValueError("rf: Path must refer to a regular file.")

    return target.read_text(encoding="utf-8")


@mcp.tool()
def write_file(path:str, content:str) -> str:
    """write utf-8 text to a file inside the experiment sandbox"""

    target = Path(path)

    if not target.is_absolute():
        raise ValueError("wf: An absolute path is required.")

    target = target.resolve(strict=False)

    if not target.is_relative_to(SANDBOX_ROOT):
        raise PermissionError("wf: Path is outside the sandbox.")

    if not target.parent.is_dir():
        raise ValueError("wf: Parent must be an existing directory.")

    if target.exists() and not target.is_file():
        raise ValueError("wf: An existing destination must be a regular file.")

    if not isinstance(content, str):
        raise TypeError("wf: 'content' must be a string.")

    try:
        content.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("wf: Content must be valid UTF-8 text.") from None

    target.write_text(data=content, encoding="utf-8")

    return "File written successfully."

@mcp.tool()
def list_directory(path:str) -> list[str]:
    "return entrynames inseide a directory in the experiment sandbox"
    target = Path(path)

    if not target.is_absolute():
        raise ValueError("ld: An absolute path is required.")

    target = target.resolve(strict=True)

    if not target.is_relative_to(SANDBOX_ROOT):
        raise PermissionError("ld: Path is outside the sandbox.")

    if not target.is_dir():
        raise ValueError("ld: Path must refer to a directory.")

    return sorted(entry.name for entry in target.iterdir())



if __name__ == "__main__":
    mcp.run(transport="stdio")
