import asyncio
import json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ollama import AsyncClient
from gateway.gateway import SecurityGateway
import sys

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

    #server parameter
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(PROJECT_ROOT),
    )

    document_path = PROJECT_ROOT / "sandbox" / "public" / "clean.txt"
    

    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
    
            # define exectutor function
            async def executor(tool_name: str, arguments: dict) -> object:
                result = await session.call_tool(
                    tool_name,
                    arguments=arguments,
                )

                if result.is_error:
                    raise RuntimeError("MCP tool execution failed.")
                return result.model_dump(mode="json")

            #init the gateway
            gateway = SecurityGateway(executor)
            
            #ask llm to use tool
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

            #execute through the gateway
            result = [
                await gateway.execute(
                call.function.name,
                call.function.arguments,
            )                
                for call in tool_calls
            ]
            print("Tool call, through gateway: ")
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
