import asyncio
import json
from pathlib import Path

from ollama import AsyncClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]

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

    document_path = PROJECT_ROOT / "sandbox" / "public" / "clean.txt"
    response = await client.chat(
        model="qwen3:1.7b",
        messages=[
            {
                "role": "user",
                "content": (
                    "Use the read_file tool to read the file at this absolute "
                    f"path: {document_path}"
                ),
            }
        ],
        tools=[READ_FILE_TOOL],
        think=False,
        options={"num_ctx": 2048},
    )

    tool_calls = response.message.tool_calls
    if not tool_calls:
        print("No tool call was proposed.")
        if response.message.content:
            print(response.message.content)
        return

    # Inspect proposals only; tool execution belongs behind the gateway.
    proposals = [
        {"name": call.function.name, "arguments": call.function.arguments}
        for call in tool_calls
    ]
    print("Proposed tool calls (not executed):")
    print(json.dumps(proposals, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
