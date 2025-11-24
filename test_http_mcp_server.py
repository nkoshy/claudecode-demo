#!/usr/bin/env python3
"""
Test HTTP MCP Server for Kubernetes tools.
"""

import asyncio
import json
from mcp import ClientSession
from mcp.client.sse import sse_client

async def test_k8s_mcp_server(server_url: str):
    """Test the Kubernetes MCP server."""

    async with sse_client(server_url) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            print(f"Connecting to {server_url}...")
            await session.initialize()
            print("✓ Connected!\n")

            # List available tools
            tools_result = await session.list_tools()
            print(f"Available tools: {len(tools_result.tools)}")

            # Find deployment and pod list tools
            deployment_tool = None
            pod_tool = None

            for tool in tools_result.tools:
                if "deployment" in tool.name.lower() and "list" in tool.name.lower():
                    deployment_tool = tool
                    print(f"  ✓ Found: {tool.name}")
                elif "pod" in tool.name.lower() and "list" in tool.name.lower():
                    pod_tool = tool
                    print(f"  ✓ Found: {tool.name}")

            # Test deployment list
            if deployment_tool:
                print(f"\n{'='*60}")
                print(f"Testing: {deployment_tool.name}")
                print(f"{'='*60}")
                try:
                    result = await session.call_tool(
                        deployment_tool.name,
                        {"namespace": "devnamespace"}
                    )
                    print(f"✓ SUCCESS!")
                    if result.content:
                        content = result.content[0].text
                        # Try to parse as JSON
                        try:
                            data = json.loads(content)
                            if isinstance(data, dict) and "items" in data:
                                print(f"  Retrieved {len(data['items'])} deployments")
                                if data['items']:
                                    print(f"  First deployment: {data['items'][0].get('metadata', {}).get('name', 'unknown')}")
                        except:
                            print(f"  Response: {content[:200]}...")
                except Exception as e:
                    print(f"✗ ERROR: {type(e).__name__}: {str(e)}")
                    if "None is not of type 'string'" in str(e):
                        print("\n❌ VALIDATION ERROR STILL EXISTS")
                        print("This means the schema needs more fixes for nullable fields")
                    import traceback
                    traceback.print_exc()

            # Test pod list
            if pod_tool:
                print(f"\n{'='*60}")
                print(f"Testing: {pod_tool.name}")
                print(f"{'='*60}")
                try:
                    result = await session.call_tool(
                        pod_tool.name,
                        {"namespace": "devnamespace"}
                    )
                    print(f"✓ SUCCESS!")
                    if result.content:
                        content = result.content[0].text
                        try:
                            data = json.loads(content)
                            if isinstance(data, dict) and "items" in data:
                                print(f"  Retrieved {len(data['items'])} pods")
                                if data['items']:
                                    print(f"  First pod: {data['items'][0].get('metadata', {}).get('name', 'unknown')}")
                        except:
                            print(f"  Response: {content[:200]}...")
                except Exception as e:
                    print(f"✗ ERROR: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    server_url = "https://k8smcp.k8smcp.cloud/mcp"
    asyncio.run(test_k8s_mcp_server(server_url))
