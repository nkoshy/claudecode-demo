#!/usr/bin/env python3
"""
Test MCP Server using streamable-http transport.
"""

import asyncio
import json
import httpx
from mcp import ClientSession
from mcp.client.session import ClientSession as BaseSession

async def streamable_http_client(url: str):
    """Simple streamable-http MCP client."""

    client = httpx.AsyncClient(timeout=30.0)

    async def send_message(message: dict):
        """Send a message to the MCP server."""
        response = await client.post(
            url,
            json=message,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        response.raise_for_status()
        return response.json()

    # Initialize
    print("Initializing MCP session...")
    init_response = await send_message({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    })
    print(f"Initialize response: {json.dumps(init_response, indent=2)}\n")

    # List tools
    print("Listing tools...")
    tools_response = await send_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    })

    tools = tools_response.get("result", {}).get("tools", [])
    print(f"Found {len(tools)} tools:")

    deployment_tool = None
    pod_tool = None

    for tool in tools[:10]:  # Show first 10
        print(f"  - {tool.get('name')}")
        if "deployment" in tool.get("name", "").lower() and "list" in tool.get("name", "").lower():
            deployment_tool = tool
            print(f"    ^ Found deployment list tool!")
        if "pod" in tool.get("name", "").lower() and "list" in tool.get("name", "").lower():
            pod_tool = tool
            print(f"    ^ Found pod list tool!")

    if len(tools) > 10:
        print(f"  ... and {len(tools) - 10} more")

    # Test deployment tool
    if deployment_tool:
        print(f"\n{'='*60}")
        print(f"Testing: {deployment_tool['name']}")
        print(f"{'='*60}")

        try:
            result = await send_message({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": deployment_tool["name"],
                    "arguments": {
                        "namespace": "devnamespace"
                    }
                }
            })

            print("✓ SUCCESS!")
            print(f"Response: {json.dumps(result, indent=2)[:500]}...")

        except Exception as e:
            print(f"✗ ERROR: {type(e).__name__}: {str(e)}")
            if "None is not of type 'string'" in str(e):
                print("\n❌ VALIDATION ERROR - Schema needs more fixes!")

    # Test pod tool
    if pod_tool:
        print(f"\n{'='*60}")
        print(f"Testing: {pod_tool['name']}")
        print(f"{'='*60}")

        try:
            result = await send_message({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": pod_tool["name"],
                    "arguments": {
                        "namespace": "devnamespace"
                    }
                }
            })

            print("✓ SUCCESS!")
            print(f"Response: {json.dumps(result, indent=2)[:500]}...")

        except Exception as e:
            print(f"✗ ERROR: {type(e).__name__}: {str(e)}")

    await client.aclose()

if __name__ == "__main__":
    url = "https://k8smcp.k8smcp.cloud/mcp"
    print(f"Connecting to: {url}\n")
    asyncio.run(streamable_http_client(url))
