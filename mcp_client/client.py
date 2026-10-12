import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(PROJECT_ROOT),
    )

    async with stdio_client(parameters) as (read, write):
        # initialize an MCP session using read and write.
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP session initialized.")
            response = await session.list_tools()

            for tool in response.tools:
                print(f"Available tool: {tool.name}")


if __name__ == "__main__":
    asyncio.run(main())
