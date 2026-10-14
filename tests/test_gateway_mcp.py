import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from gateway.gateway import SecurityGateway


@asynccontextmanager
async def connected_gateway(sandbox):
    root = sandbox["public"].parent
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
        cwd=str(Path(__file__).resolve().parents[1]),
    )

    async with asyncio.timeout(20):
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=10
            ) as session:
                await session.initialize()
                with patch.object(
                    session, "call_tool", new_callable=AsyncMock, wraps=session.call_tool
                ) as call_tool:
                    async def executor(tool_name, arguments):
                        result = await session.call_tool(tool_name, arguments=arguments)
                        if result.is_error:
                            raise RuntimeError("MCP tool execution failed.")
                        return result

                    yield SecurityGateway(executor), call_tool, session


@pytest.mark.asyncio
async def test_approved_tools_execute_over_mcp(sandbox):
    document = sandbox["public"] / "document.txt"
    destination = sandbox["output"] / "summary.txt"

    async with connected_gateway(sandbox) as (gateway, call_tool, session):
        response = await gateway.execute("read_file", {"path": str(document)})

        assert response["status"] == "success"
        assert response["reason"] is None
        assert not response["result"].is_error
        assert response["result"].structured_content == {
            "result": document.read_text(encoding="utf-8")
        }
        call_tool.assert_awaited_once_with(
            "read_file", arguments={"path": str(document.resolve())}
        )

        response = await gateway.execute(
            "list_directory", {"path": str(sandbox["public"])}
        )

        assert response["status"] == "success"
        assert response["result"].structured_content == {"result": ["document.txt"]}

        response = await gateway.execute(
            "write_file", {"path": str(destination), "content": "A public summary"}
        )

        assert response["status"] == "success"
        assert not response["result"].is_error
        assert destination.read_text(encoding="utf-8") == "A public summary"
        assert call_tool.await_count == 3


@pytest.mark.asyncio
async def test_denied_requests_never_call_mcp(sandbox):
    secret = sandbox["secrets"] / "password.txt"
    original_content = secret.read_text(encoding="utf-8")

    async with connected_gateway(sandbox) as (gateway, call_tool, session):
        # The server permits this dummy secret; the gateway must block access.
        baseline = await session.call_tool("read_file", arguments={"path": str(secret)})
        assert not baseline.is_error
        assert baseline.structured_content == {"result": original_content}
        call_tool.reset_mock()

        for tool in ("read_file", "list_directory", "write_file"):
            root = sandbox["output" if tool == "write_file" else "public"]
            target = sandbox["secrets"] if tool == "list_directory" else secret
            traversal = root / ".." / "secrets"
            if tool != "list_directory":
                traversal /= "password.txt"
            link = root / f"{tool}-escape"
            link.symlink_to(target, target_is_directory=tool == "list_directory")

            for path in (target, traversal, link):
                arguments = {"path": str(path)}
                if tool == "write_file":
                    arguments["content"] = "Must not overwrite the secret"

                response = await gateway.execute(tool, arguments)

                assert response["status"] == "denied", (tool, path)
                assert response["result"] is None
                assert response["reason"]
                call_tool.assert_not_called()

    assert secret.read_text(encoding="utf-8") == original_content


@pytest.mark.asyncio
async def test_mcp_tool_failure_returns_generic_gateway_error(sandbox):
    invalid_document = sandbox["public"] / "invalid.txt"
    invalid_document.write_bytes(b"\xff")

    async with connected_gateway(sandbox) as (gateway, call_tool, session):
        response = await gateway.execute("read_file", {"path": str(invalid_document)})

        call_tool.assert_awaited_once_with(
            "read_file", arguments={"path": str(invalid_document.resolve())}
        )
        assert response == {
            "status": "error",
            "result": None,
            "reason": "Tool execution failed.",
        }
