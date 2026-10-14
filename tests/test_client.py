from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

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
    assert capsys.readouterr().out == (
        "MCP session initialized.\n{'result': 'Public document'}\n"
    )
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_failure_raises_generic_error(client_connection, capsys):
    session, state, transport = client_connection
    session.call_tool.return_value = SimpleNamespace(
        is_error=True,
        content="Sensitive server details",
        structured_content=None,
    )

    with pytest.raises(RuntimeError, match=r"^MCP tool execution failed\.$"):
        await client.main()

    assert "Sensitive server details" not in capsys.readouterr().out
    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_error_propagates_and_closes_session(client_connection):
    session, state, transport = client_connection
    session.call_tool.side_effect = ConnectionError("Connection closed")

    with pytest.raises(ConnectionError, match="Connection closed"):
        await client.main()

    assert not state["session_active"]
    transport.__aexit__.assert_awaited_once()
