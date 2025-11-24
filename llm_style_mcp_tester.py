#!/usr/bin/env python3
"""
LLM-style MCP Tool Tester

This script simulates how an LLM would:
1. Read tool descriptions and parameter schemas
2. Understand what each tool does
3. Craft appropriate requests with correct payloads
4. Execute realistic workflows (create -> list -> get -> delete)

Purpose: Validate that docstrings are clear enough for LLM understanding
"""

import asyncio
import httpx
import json
import time
from typing import Dict, List, Any
from datetime import datetime

class MCPToolTester:
    def __init__(self, url: str):
        self.url = url
        self.client = httpx.AsyncClient(timeout=60.0)
        self.request_id = 0
        self.tools = []
        self.namespace = "devnamespace"
        self.test_results = []
        self.session_id = None  # Track session ID from server

    async def send_request(self, method: str, params: dict = None):
        """Send JSON-RPC request to MCP server (SSE transport)."""
        self.request_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        # Build headers with session ID if available
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

        # Better error handling for 4xx/5xx errors
        if response.status_code >= 400:
            print(f"\n❌ HTTP {response.status_code} Error for method: {method}")
            print(f"   Request: {json.dumps(message, indent=2)}")
            print(f"   Response: {response.text[:500]}")
            response.raise_for_status()

        # Capture session ID from initialize response
        if method == "initialize" and "mcp-session-id" in response.headers:
            self.session_id = response.headers["mcp-session-id"]
            print(f"   📌 Session ID captured: {self.session_id}")

        # Get response content
        response_text = response.text.strip()

        # Debug: print first 200 chars of response
        if not response_text:
            print(f"⚠️  Empty response for method: {method}")
            print(f"   Status: {response.status_code}")
            print(f"   Headers: {dict(response.headers)}")
            raise Exception("Empty response from server")

        # Parse SSE response
        # SSE format: "event: message\ndata: {...}\n\n"
        if response_text.startswith("event:") or "data:" in response_text:
            # Parse SSE events - handle multiple events
            lines = response_text.split('\n')
            json_data = None

            for line in lines:
                line = line.strip()
                if line.startswith('data:'):
                    data_json = line[5:].strip()  # Remove 'data:' prefix
                    if data_json:
                        try:
                            json_data = json.loads(data_json)
                            # For SSE, we might get multiple events, return the last one
                        except json.JSONDecodeError as e:
                            print(f"⚠️  Failed to parse SSE data: {data_json[:100]}")
                            continue

            if json_data:
                return json_data

        # Try plain JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # If neither SSE nor JSON, print debug info
            print(f"❌ Failed to parse response for method: {method}")
            print(f"   Response length: {len(response_text)}")
            print(f"   Response start: {response_text[:200]}")
            print(f"   Content-Type: {response.headers.get('content-type')}")
            raise

    async def send_notification(self, method: str, params: dict = None):
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }

        # Build headers with session ID if available
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        await self.client.post(
            self.url,
            json=message,
            headers=headers
        )
        # Notifications don't expect a response

    async def initialize(self):
        """Initialize MCP session."""
        print("🔌 Initializing MCP connection...")
        await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "llm-tester", "version": "1.0"}
        })

        # Send initialized notification (required by MCP protocol)
        await self.send_notification("notifications/initialized")
        print("✅ Connected\n")

    async def list_tools(self):
        """List all available tools."""
        print("📋 Fetching available tools...")
        response = await self.send_request("tools/list")
        self.tools = response.get("result", {}).get("tools", [])
        print(f"✅ Found {len(self.tools)} tools\n")
        return self.tools

    async def call_tool(self, tool_name: str, arguments: dict):
        """Call a tool with arguments."""
        response = await self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        result = response.get("result", {})
        if "content" in result:
            content = result["content"][0].get("text", "")
            try:
                return json.loads(content)
            except:
                return content
        return result

    def get_k8s_deployment_spec(self, name: str) -> dict:
        """Generate a valid Kubernetes Deployment spec."""
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "app": name,
                    "test": "mcp-llm-tester"
                }
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": {
                        "app": name
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": name
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": name,
                                "image": "nginx:latest",
                                "ports": [
                                    {
                                        "containerPort": 80
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }

    def get_k8s_service_spec(self, name: str) -> dict:
        """Generate a valid Kubernetes Service spec."""
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "app": name,
                    "test": "mcp-llm-tester"
                }
            },
            "spec": {
                "selector": {
                    "app": name
                },
                "ports": [
                    {
                        "protocol": "TCP",
                        "port": 80,
                        "targetPort": 80
                    }
                ],
                "type": "ClusterIP"
            }
        }

    def get_k8s_configmap_spec(self, name: str) -> dict:
        """Generate a valid Kubernetes ConfigMap spec."""
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "test": "mcp-llm-tester"
                }
            },
            "data": {
                "config.txt": "test configuration",
                "app.properties": "key=value\nfoo=bar"
            }
        }

    def get_k8s_secret_spec(self, name: str) -> dict:
        """Generate a valid Kubernetes Secret spec."""
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "test": "mcp-llm-tester"
                }
            },
            "type": "Opaque",
            "stringData": {
                "username": "testuser",
                "password": "testpass123"
            }
        }

    def analyze_tool(self, tool: dict) -> dict:
        """Analyze a tool like an LLM would - understand its purpose from description."""
        name = tool["name"]
        description = tool.get("description", "")
        schema = tool.get("inputSchema", {})

        # Determine operation type from name and description
        operation_type = "unknown"
        resource_type = "unknown"

        if "list" in name.lower():
            operation_type = "list"
        elif "create" in name.lower() or "post" in name.lower():
            operation_type = "create"
        elif "read" in name.lower() or "get" in name.lower():
            operation_type = "get"
        elif "replace" in name.lower() or "put" in name.lower():
            operation_type = "update"
        elif "patch" in name.lower():
            operation_type = "patch"
        elif "delete" in name.lower():
            operation_type = "delete"

        # Determine resource type
        if "pod" in name.lower():
            resource_type = "pod"
        elif "deployment" in name.lower():
            resource_type = "deployment"
        elif "service" in name.lower():
            resource_type = "service"
        elif "configmap" in name.lower():
            resource_type = "configmap"
        elif "secret" in name.lower():
            resource_type = "secret"
        elif "replicaset" in name.lower():
            resource_type = "replicaset"
        elif "statefulset" in name.lower():
            resource_type = "statefulset"
        elif "daemonset" in name.lower():
            resource_type = "daemonset"
        elif "ingress" in name.lower():
            resource_type = "ingress"

        return {
            "name": name,
            "description": description,
            "operation_type": operation_type,
            "resource_type": resource_type,
            "schema": schema,
            "requires_body": "body" in schema.get("properties", {}),
            "requires_name": "name" in schema.get("properties", {})
        }

    async def test_resource_lifecycle(self, resource_type: str, tools_by_type: dict):
        """Test a complete resource lifecycle: create -> list -> get -> delete."""

        print(f"\n{'='*60}")
        print(f"Testing {resource_type.upper()} Lifecycle")
        print(f"{'='*60}\n")

        tools = tools_by_type.get(resource_type, {})
        if not tools:
            print(f"⚠️  No tools found for {resource_type}")
            return

        test_name = f"test-{resource_type}-{int(time.time())}"
        created = False

        try:
            # 1. CREATE
            if "create" in tools:
                tool = tools["create"]
                print(f"1️⃣  CREATE: {tool['name']}")
                print(f"   Description: {tool['description'][:100]}...")

                # Craft appropriate body based on resource type
                if resource_type == "deployment":
                    body = self.get_k8s_deployment_spec(test_name)
                elif resource_type == "service":
                    body = self.get_k8s_service_spec(test_name)
                elif resource_type == "configmap":
                    body = self.get_k8s_configmap_spec(test_name)
                elif resource_type == "secret":
                    body = self.get_k8s_secret_spec(test_name)
                else:
                    print(f"   ⚠️  Skipping create - no spec template for {resource_type}")
                    body = None

                if body:
                    try:
                        result = await self.call_tool(tool['name'], {
                            "namespace": self.namespace,
                            "body": body
                        })
                        print(f"   ✅ Created: {test_name}")
                        created = True
                        self.test_results.append({
                            "resource": resource_type,
                            "operation": "create",
                            "tool": tool['name'],
                            "status": "success"
                        })
                    except Exception as e:
                        print(f"   ❌ Error: {str(e)[:100]}")
                        self.test_results.append({
                            "resource": resource_type,
                            "operation": "create",
                            "tool": tool['name'],
                            "status": "failed",
                            "error": str(e)[:100]
                        })

                await asyncio.sleep(2)  # Wait for resource to be created

            # 2. LIST
            if "list" in tools:
                tool = tools["list"]
                print(f"\n2️⃣  LIST: {tool['name']}")
                print(f"   Description: {tool['description'][:100]}...")

                try:
                    result = await self.call_tool(tool['name'], {
                        "namespace": self.namespace
                    })

                    if isinstance(result, dict) and "items" in result:
                        count = len(result["items"])
                        print(f"   ✅ Listed {count} {resource_type}(s)")

                        # Check if our created resource is in the list
                        if created:
                            found = any(item.get("metadata", {}).get("name") == test_name
                                      for item in result["items"])
                            if found:
                                print(f"   ✅ Found our test resource: {test_name}")
                            else:
                                print(f"   ⚠️  Test resource not yet visible: {test_name}")

                        self.test_results.append({
                            "resource": resource_type,
                            "operation": "list",
                            "tool": tool['name'],
                            "status": "success",
                            "count": count
                        })
                    else:
                        print(f"   ⚠️  Unexpected response format")
                        self.test_results.append({
                            "resource": resource_type,
                            "operation": "list",
                            "tool": tool['name'],
                            "status": "unexpected_format"
                        })

                except Exception as e:
                    print(f"   ❌ Error: {str(e)[:100]}")
                    self.test_results.append({
                        "resource": resource_type,
                        "operation": "list",
                        "tool": tool['name'],
                        "status": "failed",
                        "error": str(e)[:100]
                    })

            # 3. GET (read specific resource)
            if created and "get" in tools:
                tool = tools["get"]
                print(f"\n3️⃣  GET: {tool['name']}")
                print(f"   Description: {tool['description'][:100]}...")

                try:
                    result = await self.call_tool(tool['name'], {
                        "namespace": self.namespace,
                        "name": test_name
                    })

                    if isinstance(result, dict) and "metadata" in result:
                        name = result.get("metadata", {}).get("name")
                        print(f"   ✅ Retrieved: {name}")
                        self.test_results.append({
                            "resource": resource_type,
                            "operation": "get",
                            "tool": tool['name'],
                            "status": "success"
                        })
                    else:
                        print(f"   ⚠️  Unexpected response format")

                except Exception as e:
                    print(f"   ❌ Error: {str(e)[:100]}")
                    self.test_results.append({
                        "resource": resource_type,
                        "operation": "get",
                        "tool": tool['name'],
                        "status": "failed",
                        "error": str(e)[:100]
                    })

            # 4. DELETE
            if created and "delete" in tools:
                tool = tools["delete"]
                print(f"\n4️⃣  DELETE: {tool['name']}")
                print(f"   Description: {tool['description'][:100]}...")

                try:
                    result = await self.call_tool(tool['name'], {
                        "namespace": self.namespace,
                        "name": test_name
                    })
                    print(f"   ✅ Deleted: {test_name}")
                    self.test_results.append({
                        "resource": resource_type,
                        "operation": "delete",
                        "tool": tool['name'],
                        "status": "success"
                    })
                except Exception as e:
                    print(f"   ❌ Error: {str(e)[:100]}")
                    self.test_results.append({
                        "resource": resource_type,
                        "operation": "delete",
                        "tool": tool['name'],
                        "status": "failed",
                        "error": str(e)[:100]
                    })

        except Exception as e:
            print(f"❌ Lifecycle test failed: {str(e)}")

    async def run_comprehensive_tests(self):
        """Run comprehensive tests simulating LLM tool usage."""

        await self.initialize()
        tools = await self.list_tools()

        print(f"\n{'='*60}")
        print("Analyzing Tools (LLM Perspective)")
        print(f"{'='*60}\n")

        # Analyze all tools
        analyzed_tools = [self.analyze_tool(tool) for tool in tools]

        # Group by resource type and operation
        tools_by_resource = {}
        for analyzed in analyzed_tools:
            resource = analyzed["resource_type"]
            operation = analyzed["operation_type"]

            if resource not in tools_by_resource:
                tools_by_resource[resource] = {}

            tools_by_resource[resource][operation] = analyzed

        # Print analysis summary
        print("Resource Types Found:")
        for resource, operations in sorted(tools_by_resource.items()):
            if resource != "unknown":
                ops = ", ".join(sorted(operations.keys()))
                print(f"  • {resource}: {ops}")

        # Test each resource type
        resource_types = ["deployment", "service", "configmap", "secret"]

        for resource_type in resource_types:
            await self.test_resource_lifecycle(resource_type, tools_by_resource)
            await asyncio.sleep(1)  # Pause between tests

        # Print summary
        self.print_test_summary()

    def print_test_summary(self):
        """Print summary of all test results."""
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}\n")

        total = len(self.test_results)
        success = len([r for r in self.test_results if r["status"] == "success"])
        failed = len([r for r in self.test_results if r["status"] == "failed"])

        print(f"Total Operations Tested: {total}")
        print(f"✅ Successful: {success}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(success/total*100):.1f}%\n")

        # Group by resource
        by_resource = {}
        for result in self.test_results:
            resource = result["resource"]
            if resource not in by_resource:
                by_resource[resource] = []
            by_resource[resource].append(result)

        print("Results by Resource:")
        for resource, results in sorted(by_resource.items()):
            success_count = len([r for r in results if r["status"] == "success"])
            total_count = len(results)
            print(f"\n  {resource.upper()}:")
            for result in results:
                status_icon = "✅" if result["status"] == "success" else "❌"
                print(f"    {status_icon} {result['operation']}: {result['tool']}")
                if "error" in result:
                    print(f"       Error: {result['error']}")

        # Save detailed results
        with open("mcp_test_results.json", "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "success": success,
                    "failed": failed,
                    "success_rate": f"{(success/total*100):.1f}%"
                },
                "results": self.test_results
            }, f, indent=2)

        print(f"\n📄 Detailed results saved to: mcp_test_results.json")

    async def close(self):
        """Close the client."""
        await self.client.aclose()


async def main():
    """Run the comprehensive MCP tool tests."""

    print(f"""
{'='*60}
LLM-Style MCP Tool Tester
{'='*60}
Purpose: Test MCP tools from an LLM's perspective

This script will:
1. Analyze tool descriptions like an LLM would
2. Understand what each tool does
3. Craft appropriate Kubernetes API payloads
4. Test realistic workflows:
   - Create resources (Deployment, Service, ConfigMap, Secret)
   - List resources in namespace
   - Get specific resources
   - Delete resources

Namespace: devnamespace
Server: https://k8smcp.k8smcp.cloud/mcp
{'='*60}
""")

    tester = MCPToolTester("https://k8smcp.k8smcp.cloud/mcp")

    try:
        await tester.run_comprehensive_tests()
    finally:
        await tester.close()
        print("\n✅ Testing complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
