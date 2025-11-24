#!/usr/bin/env python3
"""
Test script to list deployments in devnamespace using the MCP server.
"""

import asyncio
import httpx
import json
import os
import sys

async def list_deployments(namespace: str):
    """List deployments in a namespace via the MCP server."""

    url = "https://k8smcp.k8smcp.cloud/mcp"
    client = httpx.AsyncClient(timeout=30.0)

    async def send_message(message: dict):
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

    try:
        print(f"🔌 Connecting to MCP server at {url}...")

        # Initialize
        init_response = await send_message({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0"
                }
            }
        })
        print("✅ Connected!")

        # List tools
        print("\n📋 Fetching available tools...")
        tools_response = await send_message({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        })

        # Find deployment list tool
        deployment_tool = None
        for tool in tools_response.get("result", {}).get("tools", []):
            if "deployment" in tool["name"].lower() and "list" in tool["name"].lower():
                deployment_tool = tool["name"]
                print(f"✅ Found tool: {deployment_tool}")
                break

        if not deployment_tool:
            print("❌ Deployment list tool not found")
            print("\nAvailable tools:")
            for tool in tools_response.get("result", {}).get("tools", [])[:10]:
                print(f"  - {tool['name']}")
            return

        # Call the tool to list deployments
        print(f"\n🚀 Listing deployments in namespace '{namespace}'...")
        result_response = await send_message({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": deployment_tool,
                "arguments": {
                    "namespace": namespace
                }
            }
        })

        # Parse and display results
        result = result_response.get("result", {})

        if "content" in result:
            content = result["content"][0].get("text", "")
            try:
                data = json.loads(content)
                items = data.get("items", [])

                print(f"\n✅ SUCCESS! Found {len(items)} deployment(s) in '{namespace}':\n")

                if items:
                    for i, item in enumerate(items, 1):
                        metadata = item.get("metadata", {})
                        spec = item.get("spec", {})
                        status = item.get("status", {})

                        name = metadata.get("name", "unknown")
                        replicas = spec.get("replicas", 0)
                        ready = status.get("readyReplicas", 0)

                        print(f"{i}. {name}")
                        print(f"   Replicas: {ready}/{replicas}")
                        print(f"   Created: {metadata.get('creationTimestamp', 'unknown')}")
                        print()
                else:
                    print(f"No deployments found in namespace '{namespace}'")

            except json.JSONDecodeError:
                print(f"Response: {content[:500]}...")
        else:
            print(f"Unexpected response: {result}")

    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e.response.status_code}")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await client.aclose()

if __name__ == "__main__":
    namespace = sys.argv[1] if len(sys.argv) > 1 else "devnamespace"
    asyncio.run(list_deployments(namespace))
