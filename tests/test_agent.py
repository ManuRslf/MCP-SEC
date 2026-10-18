import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import CallToolResult, TextContent
from ollama import ChatResponse

from agent import agent


pytestmark = pytest.mark.asyncio


@pytest.fixture
def agent_runtime(monkeypatch, sandbox):
    state = {"transport": False, "session": False, "initialized": False}

    async def initialize():
        assert state["transport"] and state["session"]
        state["initialized"] = True

    async def call_tool(tool_name, arguments):
        assert state["session"] and state["initialized"]
        return session.call_tool.return_value

    async def chat(**kwargs):
        assert state["session"] and state["initialized"]
        return client.chat.return_value

    session = SimpleNamespace(
        initialize=AsyncMock(side_effect=initialize),
        call_tool=AsyncMock(side_effect=call_tool),
    )
    session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="Public test document")],
    )
    path = str(sandbox["public"] / "document.txt")
    client = SimpleNamespace(chat=AsyncMock(side_effect=chat))
    client.chat.return_value = response_with_calls([
        {"function": {"name": "read_file", "arguments": {"path": path}}},
    ])

    @asynccontextmanager
    async def transport(parameters):
        state["transport"] = True
        try:
            yield "read-stream", "write-stream"
        finally:
            state["transport"] = False

    @asynccontextmanager
    async def connection(read, write):
        assert state["transport"]
        state["session"] = True
        try:
            yield session
        finally:
            state["session"] = False

    client_factory = MagicMock(return_value=client)
    transport_factory = MagicMock(side_effect=transport)
    session_factory = MagicMock(side_effect=connection)
    gateway_factory = MagicMock(wraps=agent.SecurityGateway)
    monkeypatch.setattr(agent, "AsyncClient", client_factory)
    monkeypatch.setattr(agent, "stdio_client", transport_factory)
    monkeypatch.setattr(agent, "ClientSession", session_factory)
    monkeypatch.setattr(agent, "SecurityGateway", gateway_factory)

    yield SimpleNamespace(
        client=client,
        session=session,
        path=path,
        sandbox=sandbox,
        client_factory=client_factory,
        transport_factory=transport_factory,
        session_factory=session_factory,
        gateway_factory=gateway_factory,
    )

    assert not state["transport"]
    assert not state["session"]


def response_with_calls(tool_calls, content=""):
    return ChatResponse(
        message={
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        },
    )


def read_results(capsys):
    heading, payload = capsys.readouterr().out.split("\n", 1)
    assert heading.strip() == "Tool call, through gateway:"
    return json.loads(payload)


async def test_request_describes_read_file_and_targets_clean_document(agent_runtime):
    await agent.main()

    agent_runtime.client_factory.assert_called_once_with(
        host="http://localhost:11434", timeout=120,
    )
    parameters = agent_runtime.transport_factory.call_args.args[0]
    assert parameters.command == agent.sys.executable
    assert parameters.args == ["-m", "mcp_server.server"]
    assert parameters.cwd == str(agent.PROJECT_ROOT)
    agent_runtime.session_factory.assert_called_once_with("read-stream", "write-stream")
    agent_runtime.session.initialize.assert_awaited_once()
    agent_runtime.gateway_factory.assert_called_once()
    agent_runtime.client.chat.assert_awaited_once()
    request = agent_runtime.client.chat.await_args.kwargs
    assert request["model"] == "qwen3:1.7b"
    assert request["think"] is False
    assert request["options"] == {"num_ctx": 2048}
    path = agent.PROJECT_ROOT / "sandbox" / "public" / "clean.txt"
    assert path.is_absolute()
    assert request["messages"] == [
        {
            "role": "user",
            "content": f"Use the read_file tool to read the file at this absolute path: {path}",
        },
    ]
    assert len(request["tools"]) == 1
    tool = request["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "read_file"
    parameters = tool["function"]["parameters"]
    assert parameters["type"] == "object"
    assert parameters["required"] == ["path"]
    assert set(parameters["properties"]) == {"path"}
    assert parameters["properties"]["path"]["type"] == "string"
    assert parameters["additionalProperties"] is False


async def test_approved_model_call_returns_json_serializable_mcp_result(agent_runtime, capsys):
    await agent.main()

    agent_runtime.session.call_tool.assert_awaited_once_with(
        "read_file", arguments={"path": agent_runtime.path},
    )
    result = read_results(capsys)
    assert result == [{
        "status": "success",
        "result": agent_runtime.session.call_tool.return_value.model_dump(mode="json"),
        "reason": None,
    }]


async def test_every_proposed_call_goes_through_gateway_in_order(agent_runtime, capsys):
    proposals = [
        {"name": "read_file", "arguments": {"path": agent_runtime.path}},
        {"name": "unknown_tool", "arguments": {"value": "inspection only"}},
    ]
    agent_runtime.client.chat.return_value = response_with_calls([
        {"function": proposal} for proposal in proposals
    ])

    await agent.main()

    results = read_results(capsys)
    assert [result["status"] for result in results] == ["success", "denied"]
    assert results[1]["result"] is None
    agent_runtime.session.call_tool.assert_awaited_once_with(
        "read_file", arguments={"path": agent_runtime.path},
    )
    agent_runtime.client.chat.assert_awaited_once()


@pytest.mark.parametrize("tool_name", ["read_file", "unknown_tool"])
async def test_denied_model_call_never_invokes_mcp(agent_runtime, capsys, tool_name):
    secret_path = str(agent_runtime.sandbox["secrets"] / "password.txt")
    agent_runtime.client.chat.return_value = response_with_calls([
        {"function": {"name": tool_name, "arguments": {"path": secret_path}}},
    ])

    await agent.main()

    result = read_results(capsys)
    assert len(result) == 1
    assert result[0]["status"] == "denied"
    assert result[0]["result"] is None
    agent_runtime.session.call_tool.assert_not_called()


async def test_mcp_error_result_is_sanitized(agent_runtime, capsys):
    agent_runtime.session.call_tool.return_value = CallToolResult(
        is_error=True,
        content=[TextContent(type="text", text="Sensitive tool failure details")],
    )

    await agent.main()

    assert read_results(capsys) == [{
        "status": "error", "result": None, "reason": "Tool execution failed.",
    }]
    agent_runtime.session.call_tool.assert_awaited_once()


async def test_mcp_connection_failure_is_sanitized(agent_runtime, capsys):
    agent_runtime.session.call_tool.side_effect = RuntimeError("Sensitive connection details")

    await agent.main()

    assert read_results(capsys) == [{
        "status": "error", "result": None, "reason": "Tool execution failed.",
    }]


@pytest.mark.parametrize("tool_calls", [None, []])
async def test_reports_text_only_reply_without_calling_mcp(agent_runtime, capsys, tool_calls):
    agent_runtime.client.chat.return_value = response_with_calls(
        tool_calls, "No proposal this time.",
    )

    await agent.main()

    assert capsys.readouterr().out == "No tool call was proposed.\nNo proposal this time.\n"
    agent_runtime.client.chat.assert_awaited_once()
    agent_runtime.session.call_tool.assert_not_called()


async def test_reports_empty_reply_without_calling_mcp(agent_runtime, capsys):
    agent_runtime.client.chat.return_value = response_with_calls(None)

    await agent.main()

    assert capsys.readouterr().out == "No tool call was proposed.\n"
    agent_runtime.session.call_tool.assert_not_called()


@pytest.mark.parametrize("error", [ConnectionError("Ollama unavailable"), asyncio.CancelledError()])
async def test_propagates_model_failure_and_closes_connections(agent_runtime, capsys, error):
    agent_runtime.client.chat.side_effect = error

    with pytest.raises(type(error)):
        await agent.main()

    assert capsys.readouterr().out == ""
    agent_runtime.client.chat.assert_awaited_once()
    agent_runtime.session.call_tool.assert_not_called()


async def test_initialization_failure_stops_before_model_request(agent_runtime, capsys):
    agent_runtime.session.initialize.side_effect = RuntimeError("Initialization failed")

    with pytest.raises(RuntimeError, match="Initialization failed"):
        await agent.main()

    assert capsys.readouterr().out == ""
    agent_runtime.client.chat.assert_not_called()
    agent_runtime.session.call_tool.assert_not_called()


async def test_mcp_cancellation_propagates_and_closes_connections(agent_runtime, capsys):
    agent_runtime.session.call_tool.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await agent.main()

    assert capsys.readouterr().out == ""
    agent_runtime.session.call_tool.assert_awaited_once()
