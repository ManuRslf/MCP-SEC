import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ollama import AsyncClient

from gateway.gateway import SecurityGateway


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_MODEL_TURNS = 5
MAX_TOOL_CALLS = 10

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read the UTF-8 contents of a file using its absolute path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute path to the file to read.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


async def main() -> None:
    client = AsyncClient(
        host="http://localhost:11434",
        timeout=120,
    )

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(PROJECT_ROOT),
    )

    document_path = PROJECT_ROOT / "sandbox" / "public" / "clean.txt"
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def executor(tool_name: str, arguments: dict) -> object:
                result = await session.call_tool(
                    tool_name,
                    arguments=arguments,
                )

                if result.is_error:
                    raise RuntimeError("MCP tool execution failed.")
                return result.model_dump(mode="json")

            gateway = SecurityGateway(executor)
            messages = [
                {
                    "role": "user",
                    "content": (
                        f"Read the file at {document_path} using read_file, "
                        "then summarize its contents in two sentences."
                    ),
                },
            ]

            tool_calls_used = 0
            for turn in range(MAX_MODEL_TURNS):
                reply = await client.chat(
                    model="qwen3:1.7b",
                    messages=messages,
                    tools=[READ_FILE_TOOL],
                    think=False,
                    options={"num_ctx": 2048},
                )
                messages.append(reply.message)

                tool_calls = reply.message.tool_calls
                if not tool_calls:
                    if tool_calls_used == 0:
                        print("No tool call was proposed.")
                    if reply.message.content:
                        print(reply.message.content)
                    elif tool_calls_used:
                        print("The model returned no final answer.")
                    return

                # Reserve a model turn to consume results before executing tools.
                if turn == MAX_MODEL_TURNS - 1:
                    break

                # Reject a whole batch rather than executing only some requests.
                if tool_calls_used + len(tool_calls) > MAX_TOOL_CALLS:
                    print("Tool call limit reached; no final answer was produced.")
                    return

                for call in tool_calls:
                    tool_calls_used += 1
                    result = await gateway.execute(
                        call.function.name,
                        call.function.arguments,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_name": call.function.name,
                        "content": json.dumps(result),
                    })

            print("Model turn limit reached; no final answer was produced.")


if __name__ == "__main__":
    asyncio.run(main())
