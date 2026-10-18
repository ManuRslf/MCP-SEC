import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ollama import ChatResponse

from agent import agent


pytestmark = pytest.mark.asyncio


@pytest.fixture
def ollama_client(monkeypatch):
    client = SimpleNamespace(chat=AsyncMock())
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(agent, "AsyncClient", factory)
    return client, factory


def response_with_calls(tool_calls, content=""):
    return ChatResponse(
        message={
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        },
    )


def read_proposals(capsys):
    heading, payload = capsys.readouterr().out.split("\n", 1)
    assert heading == "Proposed tool calls (not executed):"
    return json.loads(payload)


async def test_request_describes_read_file_and_targets_clean_document(ollama_client):
    client, factory = ollama_client
    client.chat.return_value = response_with_calls([])

    await agent.main()

    factory.assert_called_once_with(host="http://localhost:11434", timeout=120)
    client.chat.assert_awaited_once()
    request = client.chat.await_args.kwargs
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


async def test_prints_proposal_without_reading_files(ollama_client, capsys):
    client, _ = ollama_client
    path = str(agent.PROJECT_ROOT / "sandbox" / "public" / "clean.txt")
    client.chat.return_value = response_with_calls([
        {"function": {"name": "read_file", "arguments": {"path": path}}},
    ])

    with (
        patch("builtins.open", side_effect=AssertionError("No file reads allowed")) as file_open,
        patch.object(Path, "open", side_effect=AssertionError("No file reads allowed")) as path_open,
    ):
        await agent.main()

    file_open.assert_not_called()
    path_open.assert_not_called()
    client.chat.assert_awaited_once()
    assert read_proposals(capsys) == [
        {"name": "read_file", "arguments": {"path": path}},
    ]


async def test_prints_every_proposal_without_dispatching_unknown_tools(ollama_client, capsys):
    client, _ = ollama_client
    proposals = [
        {"name": "read_file", "arguments": {"path": "/example/public/clean.txt"}},
        {"name": "unknown_tool", "arguments": {"value": "inspection only"}},
    ]
    client.chat.return_value = response_with_calls([
        {"function": proposal} for proposal in proposals
    ])

    await agent.main()

    assert read_proposals(capsys) == proposals
    client.chat.assert_awaited_once()


@pytest.mark.parametrize("tool_calls", [None, []])
async def test_reports_text_only_reply(ollama_client, capsys, tool_calls):
    client, _ = ollama_client
    client.chat.return_value = response_with_calls(tool_calls, "No proposal this time.")

    await agent.main()

    assert capsys.readouterr().out == "No tool call was proposed.\nNo proposal this time.\n"
    client.chat.assert_awaited_once()


async def test_reports_empty_reply(ollama_client, capsys):
    client, _ = ollama_client
    client.chat.return_value = response_with_calls(None)

    await agent.main()

    assert capsys.readouterr().out == "No tool call was proposed.\n"


@pytest.mark.parametrize("error", [ConnectionError("Ollama unavailable"), asyncio.CancelledError()])
async def test_propagates_request_failure_without_printing_a_proposal(ollama_client, capsys, error):
    client, _ = ollama_client
    client.chat.side_effect = error

    with pytest.raises(type(error)):
        await agent.main()

    assert capsys.readouterr().out == ""
    client.chat.assert_awaited_once()
