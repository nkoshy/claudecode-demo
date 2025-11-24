#!/usr/bin/env python3
"""
Interactive MCP Client for testing Kubernetes operations.

This client lets you:
- List all available tools
- View tool descriptions and parameters
- Call tools interactively
- See raw responses for debugging docstrings

Usage:
    python interactive_mcp_client.py
"""

import asyncio
import httpx
import json
from typing import Optional

class MCPClient:
    def __init__(self, url: str):
        self.url = url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.request_id = 0
        self.tools = []
        self.session_id = None

    async def send_request(self, method: str, params: dict = None):
        """Send a JSON-RPC request to the MCP server."""
        self.request_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        # Include session ID if available
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        response = await self.client.post(
            self.url,
            json=message,
            headers=headers
        )
        response.raise_for_status()

        # Capture session ID from initialize
        if method == "initialize" and "mcp-session-id" in response.headers:
            self.session_id = response.headers["mcp-session-id"]

        return response.json()

    async def initialize(self):
        """Initialize the MCP session."""
        print("🔌 Connecting to MCP server...")
        response = await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "interactive-test-client",
                "version": "1.0"
            }
        })

        # Send initialized notification (required by MCP protocol)
        await self.send_notification("notifications/initialized")
        print("✅ Connected!\n")
        return response

    async def send_notification(self, method: str, params: dict = None):
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        await self.client.post(self.url, json=message, headers=headers)

    async def list_tools(self):
        """List all available tools."""
        print("📋 Fetching available tools...")
        response = await self.send_request("tools/list")
        self.tools = response.get("result", {}).get("tools", [])
        print(f"✅ Found {len(self.tools)} tools\n")
        return self.tools

    async def call_tool(self, tool_name: str, arguments: dict):
        """Call a specific tool."""
        print(f"🚀 Calling tool: {tool_name}")
        print(f"   Arguments: {json.dumps(arguments, indent=2)}\n")

        response = await self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        result = response.get("result", {})
        if "content" in result:
            content = result["content"][0].get("text", "")
            try:
                data = json.loads(content)
                # FastMCP wraps K8s responses in {"result": {...}}
                # Unwrap if present
                if isinstance(data, dict) and "result" in data and len(data) == 1:
                    return data["result"]
                return data
            except:
                return content
        return result

    async def close(self):
        """Close the client."""
        await self.client.aclose()


async def interactive_session(url: str):
    """Run an interactive testing session."""
    client = MCPClient(url)

    try:
        # Initialize
        await client.initialize()

        # List tools
        tools = await client.list_tools()

        while True:
            print("\n" + "="*60)
            print("MCP Interactive Test Client")
            print("="*60)
            print("Commands:")
            print("  1. List all tools")
            print("  2. Search tools by keyword")
            print("  3. View tool details")
            print("  4. Call a tool")
            print("  5. Test common operations")
            print("  q. Quit")
            print()

            choice = input("Enter choice: ").strip()

            if choice == "q":
                break

            elif choice == "1":
                # List all tools
                print(f"\n📋 Available Tools ({len(tools)}):\n")
                for i, tool in enumerate(tools, 1):
                    print(f"{i:3d}. {tool['name']}")
                    if tool.get("description"):
                        desc = tool["description"][:80]
                        print(f"      {desc}...")

            elif choice == "2":
                # Search tools
                keyword = input("\nEnter keyword to search: ").strip().lower()
                matching = [t for t in tools if keyword in t["name"].lower() or
                           keyword in t.get("description", "").lower()]

                print(f"\n🔍 Found {len(matching)} matching tools:\n")
                for i, tool in enumerate(matching, 1):
                    print(f"{i}. {tool['name']}")
                    if tool.get("description"):
                        print(f"   {tool['description'][:100]}...")

            elif choice == "3":
                # View tool details
                tool_name = input("\nEnter tool name: ").strip()
                tool = next((t for t in tools if t["name"] == tool_name), None)

                if tool:
                    print(f"\n📖 Tool: {tool['name']}")
                    print("="*60)
                    print(f"\nDescription:")
                    print(f"  {tool.get('description', 'No description')}")

                    if "inputSchema" in tool:
                        print(f"\nParameters:")
                        schema = tool["inputSchema"]
                        if "properties" in schema:
                            for param, details in schema["properties"].items():
                                required = param in schema.get("required", [])
                                req_marker = " (required)" if required else ""
                                param_type = details.get("type", "unknown")
                                param_desc = details.get("description", "")
                                print(f"  - {param}{req_marker}: {param_type}")
                                if param_desc:
                                    print(f"    {param_desc}")

                    # Show raw schema
                    print(f"\nRaw Input Schema:")
                    print(json.dumps(tool.get("inputSchema", {}), indent=2))
                else:
                    print(f"❌ Tool '{tool_name}' not found")

            elif choice == "4":
                # Call a tool
                tool_name = input("\nEnter tool name: ").strip()
                tool = next((t for t in tools if t["name"] == tool_name), None)

                if not tool:
                    print(f"❌ Tool '{tool_name}' not found")
                    continue

                # Build arguments
                arguments = {}
                schema = tool.get("inputSchema", {})
                properties = schema.get("properties", {})
                required = schema.get("required", [])

                print("\nEnter arguments (leave blank to skip optional parameters):")
                for param, details in properties.items():
                    is_required = param in required
                    req_marker = " (required)" if is_required else " (optional)"
                    param_type = details.get("type", "string")

                    value = input(f"  {param}{req_marker} [{param_type}]: ").strip()

                    if value or is_required:
                        # Type conversion
                        if param_type == "integer":
                            arguments[param] = int(value) if value else 0
                        elif param_type == "boolean":
                            arguments[param] = value.lower() in ["true", "1", "yes"]
                        else:
                            arguments[param] = value

                # Call the tool
                try:
                    result = await client.call_tool(tool_name, arguments)

                    print("\n✅ Success!")
                    print("\nResult:")
                    print(json.dumps(result, indent=2)[:2000])

                    # If it's a list result, show count
                    if isinstance(result, dict) and "items" in result:
                        print(f"\nReturned {len(result['items'])} items")

                except Exception as e:
                    print(f"\n❌ Error: {str(e)}")

            elif choice == "5":
                # Test common operations
                print("\n🧪 Common Test Operations:")
                print("  1. List pods in devnamespace")
                print("  2. List deployments in devnamespace")
                print("  3. List services in devnamespace")
                print("  4. List configmaps in devnamespace")

                test_choice = input("\nEnter test number: ").strip()

                tests = {
                    "1": ("listCoreV1NamespacedPod", {"namespace": "devnamespace"}),
                    "2": ("listAppsV1NamespacedDeployment", {"namespace": "devnamespace"}),
                    "3": ("listCoreV1NamespacedService", {"namespace": "devnamespace"}),
                    "4": ("listCoreV1NamespacedConfigMap", {"namespace": "devnamespace"}),
                }

                if test_choice in tests:
                    tool_name, arguments = tests[test_choice]
                    try:
                        result = await client.call_tool(tool_name, arguments)
                        print("\n✅ Success!")

                        if isinstance(result, dict) and "items" in result:
                            items = result["items"]
                            print(f"\nFound {len(items)} items:")
                            for i, item in enumerate(items[:10], 1):
                                name = item.get("metadata", {}).get("name", "unknown")
                                print(f"  {i}. {name}")
                            if len(items) > 10:
                                print(f"  ... and {len(items) - 10} more")
                        else:
                            print(json.dumps(result, indent=2)[:1000])

                    except Exception as e:
                        print(f"\n❌ Error: {str(e)}")
                        import traceback
                        traceback.print_exc()

            input("\nPress Enter to continue...")

    finally:
        await client.close()


if __name__ == "__main__":
    SERVER_URL = "https://k8smcp.k8smcp.cloud/mcp"

    print(f"""
{'='*60}
Interactive MCP Test Client
{'='*60}
Server: {SERVER_URL}
Purpose: Test MCP tools and review docstrings

This client helps you:
- Browse all available Kubernetes tools
- Test operations with your cluster
- Review tool descriptions and parameters
- Debug responses for docstring improvements
{'='*60}
""")

    try:
        asyncio.run(interactive_session(SERVER_URL))
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
