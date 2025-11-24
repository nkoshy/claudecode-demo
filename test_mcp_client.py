#!/usr/bin/env python3
"""
MCP Client to test Kubernetes FastMCP server tools.

This client connects to a FastMCP server and tests the listAppsV1NamespacedDeployment tool
to diagnose validation errors.
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_list_deployments(server_command: list[str], namespace: str = "devnamespace"):
    """Test the listAppsV1NamespacedDeployment tool."""

    server_params = StdioServerParameters(
        command=server_command[0],
        args=server_command[1:] if len(server_command) > 1 else [],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()

            # List available tools
            tools_result = await session.list_tools()
            print(f"Available tools: {len(tools_result.tools)}")

            # Find the deployment list tool
            deploy_tool = None
            for tool in tools_result.tools:
                print(f"  - {tool.name}")
                if "deployment" in tool.name.lower() and "list" in tool.name.lower():
                    deploy_tool = tool
                    print(f"    ^ Found deployment list tool: {tool.name}")

            if not deploy_tool:
                print("\nERROR: Could not find deployment list tool")
                return

            print(f"\nTesting tool: {deploy_tool.name}")
            print(f"Description: {deploy_tool.description}")
            print(f"Input schema: {json.dumps(deploy_tool.inputSchema, indent=2)}")

            # Call the tool
            print(f"\nCalling tool with namespace={namespace}...")
            try:
                result = await session.call_tool(deploy_tool.name, {"namespace": namespace})
                print(f"\n✓ SUCCESS!")
                print(f"Result type: {type(result)}")
                print(f"Result: {json.dumps(result.content[0].text if result.content else str(result), indent=2)[:500]}...")

            except Exception as e:
                print(f"\n✗ ERROR: {type(e).__name__}: {str(e)}")
                print(f"\nFull error:")
                import traceback
                traceback.print_exc()

                # Try to extract which field caused the issue
                error_str = str(e)
                if "None is not of type 'string'" in error_str:
                    print("\n❌ This is the validation error we need to fix!")
                    print("The response contains a null value in a field defined as type: 'string'")

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python test_mcp_client.py <server_command> [namespace]")
        print("\nExample:")
        print("  python test_mcp_client.py 'fastmcp run' devnamespace")
        print("  python test_mcp_client.py 'python server.py' devnamespace")
        sys.exit(1)

    server_cmd = sys.argv[1].split()
    namespace = sys.argv[2] if len(sys.argv) > 2 else "devnamespace"

    asyncio.run(test_list_deployments(server_cmd, namespace))
