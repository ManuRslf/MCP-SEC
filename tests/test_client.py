import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from gateway import policy
from mcp_client import client


@pytest.fixture
def client_connection(monkeypatch):
    streams = (object(), object())
    state = {"session_active": False}
    session = SimpleNamespace(
        initialize=AsyncMock(),
        call_tool=AsyncMock(),
    )
    transport = MagicMock()
    transport.__aenter__ = AsyncMock(return_value=streams)
    transport.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(client, "stdio_client", Mock(return_value=transport))

    @asynccontextmanager
    async def open_session(read, write):
        assert (read, write) == streams
        state["session_active"] = True
        try:
            yield session
        finally:
            state["session_active"] = False

    monkeypatch.setattr(client, "ClientSession", open_session)
    return session, state, transport


@pytest.mark.asyncio
async def test_read_runs_inside_initialized_session(client_connection, capsys):
    session, state, transport = client_connection
    result = SimpleNamespace(
        is_error=False,
        structured_content={"result": "Public document"},
    )

    async def call_tool(tool_name, arguments):
        assert state["session_active"]
        session.initialize.assert_awaited_once_with()
        return result

    session.call_tool.side_effect = call_tool

    await client.main()

    path = client.PROJECT_ROOT / "sandbox" / "public" / "useful_data.txt"
    session.call_tool.assert_awaited_once_with(
        "read_file", arguments={"path": str(path)}
    )
    expected_response = {"status": "success", "result": result, "reason": None}
    assert capsys.readouterr().out == f"MCP session initialized.\n{expected_response}\n"
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
async def test_tool_failure_returns_generic_gateway_error(client_connection, capsys):
    session, state, transport = client_connection
    session.call_tool.return_value = SimpleNamespace(
        is_error=True,
        content="Sensitive server details",
        structured_content=None,
    )

    await client.main()

    captured = capsys.readouterr()
    expected_response = {
        "status": "error", "result": None, "reason": "Tool execution failed."
    }
    assert captured.out == f"MCP session initialized.\n{expected_response}\n"
    assert "Sensitive server details" not in captured.out + captured.err
    session.call_tool.assert_awaited_once()
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
async def test_connection_error_returns_generic_gateway_error(client_connection, capsys):
    session, state, transport = client_connection
    session.call_tool.side_effect = ConnectionError("Sensitive connection details")

    await client.main()

    captured = capsys.readouterr()
    expected_response = {
        "status": "error", "result": None, "reason": "Tool execution failed."
    }
    assert captured.out == f"MCP session initialized.\n{expected_response}\n"
    assert "Sensitive connection details" not in captured.out + captured.err
    session.call_tool.assert_awaited_once()
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
async def test_policy_denial_never_calls_mcp(client_connection, monkeypatch, tmp_path, capsys):
    session, state, transport = client_connection
    monkeypatch.setitem(policy.ALLOWED_ROOTS, "read_file", tmp_path)

    await client.main()

    assert "'status': 'denied'" in capsys.readouterr().out
    session.call_tool.assert_not_called()
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
async def test_cancellation_propagates_and_closes_session(client_connection):
    session, state, transport = client_connection
    session.call_tool.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await client.main()

    session.call_tool.assert_awaited_once()
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialization_failure_closes_session_without_tool_call(client_connection):
    session, state, transport = client_connection
    session.initialize.side_effect = ConnectionError("Initialization failed")

    with pytest.raises(ConnectionError, match="Initialization failed"):
        await client.main()

    session.call_tool.assert_not_called()
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once()
