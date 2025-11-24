#!/usr/bin/env python3
"""
Kubernetes FastMCP Server using fixed OpenAPI specs.
Uses the aggressive mode fixed specs to handle null values in K8s responses.
"""

import json
import httpx
from fastmcp import FastMCP

# Load the AGGRESSIVE MODE fixed OpenAPI specs
# These have all string fields marked as nullable to handle K8s null responses
with open("fastmcp-fixed-specs/core-v1-openapi.json") as f:
    core_spec = json.load(f)

with open("fastmcp-fixed-specs/apps-v1-openapi.json") as f:
    apps_spec = json.load(f)

with open("fastmcp-fixed-specs/networking-v1-openapi.json") as f:
    networking_spec = json.load(f)

# Create HTTP client for Kubernetes API
# Configure with your cluster details
k8s_api_server = "https://devtest-dns-6fbggdfo.hcp.eastus2.azmk8s.io"
k8s_token = "your-token-here"  # Set via environment variable in production

client = httpx.AsyncClient(
    base_url=k8s_api_server,
    headers={"Authorization": f"Bearer {k8s_token}"},
    verify=False,  # Set to True with proper CA cert in production
)

# Create FastMCP servers from the fixed specs
mcp_core = FastMCP.from_openapi(core_spec, client, name="k8s-core")
mcp_apps = FastMCP.from_openapi(apps_spec, client, name="k8s-apps")
mcp_networking = FastMCP.from_openapi(networking_spec, client, name="k8s-networking")

if __name__ == "__main__":
    # Run the server
    # FastMCP will automatically expose all the tools
    print("Starting Kubernetes MCP Server...")
    print(f"Core API: {len(core_spec.get('paths', {}))} paths")
    print(f"Apps API: {len(apps_spec.get('paths', {}))} paths")
    print(f"Networking API: {len(networking_spec.get('paths', {}))} paths")

    # Run with uvicorn or your preferred ASGI server
    import uvicorn

    # Combine all MCPs into one app if needed
    # Or run them separately on different ports
    mcp_apps.run()
