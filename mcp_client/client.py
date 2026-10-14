import asyncio
import sys
from pathlib import Path
from gateway.gateway import SecurityGateway
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
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP session initialized.")

            async def executor(tool_name: str, arguments: dict) -> object:
                result = await session.call_tool(
                    tool_name,
                    arguments=arguments,
                )

                if result.is_error:
                    raise RuntimeError("MCP tool execution failed.")
                return result

            path = PROJECT_ROOT / "sandbox" / "public" / "useful_data.txt"
            gateway = SecurityGateway(executor)
            response = await gateway.execute("read_file", {"path": str(path)})
            print(response)


if __name__ == "__main__":
    asyncio.run(main())
