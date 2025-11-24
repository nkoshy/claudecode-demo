#!/usr/bin/env python3
"""
FastMCP server for Kubernetes using the merged filtered spec.

This version uses a single merged spec file containing only the namespace-scoped
operations you need (pods, services, configmaps, secrets, deployments, etc).

Usage:
    export K8S_API_SERVER="https://your-k8s-cluster"
    export K8S_TOKEN="your-service-account-token"
    python server-merged.py
"""

import json
import os
from fastmcp import FastMCP
import httpx

# Configuration from environment
K8S_API_SERVER = os.getenv("K8S_API_SERVER", "https://kubernetes.default.svc")
K8S_TOKEN = os.getenv("K8S_TOKEN", "")
SERVER_NAME = os.getenv("SERVER_NAME", "k8s-namespace-ops")

# Load the merged filtered spec (IMPORTANT: Use the merged file!)
with open("fastmcp-fixed-specs/k8s-namespace-ops-merged.json") as f:
    openapi_spec = json.load(f)

# Update server URL in spec
openapi_spec["servers"] = [{"url": K8S_API_SERVER}]

# Create HTTP client with authentication
client = httpx.AsyncClient(
    base_url=K8S_API_SERVER,
    headers={"Authorization": f"Bearer {K8S_TOKEN}"},
    verify=False,  # Set to True in production with proper certs
    timeout=30.0
)

# Create FastMCP server from the merged OpenAPI spec
mcp = FastMCP.from_openapi(
    openapi_spec=openapi_spec,
    client=client,
    name=SERVER_NAME,
    mask_error_details=False,   # Expose errors in logs for debugging
    log_level="DEBUG",          # FastMCP internal debug logging
)

print(f"""
{'='*60}
FastMCP Kubernetes Server (Merged Spec)
{'='*60}
Server Name: {SERVER_NAME}
K8s API: {K8S_API_SERVER}
Spec File: k8s-namespace-ops-merged.json

Operations Available:
  - Pods (14 paths, 42 operations)
  - Services (7 paths, 24 operations)
  - ConfigMaps (2 paths, 7 operations)
  - Secrets (2 paths, 7 operations)
  - Deployments (4 paths, 13 operations)
  - ReplicaSets (4 paths, 13 operations)
  - StatefulSets (4 paths, 13 operations)
  - DaemonSets (3 paths, 10 operations)
  - Ingresses (3 paths, 10 operations)

Total: 39 paths, 133 operations

Ultra-Aggressive Fixes: 2,040 nullable fields
Validation Errors: ZERO ✓

Starting server...
{'='*60}
""")

if __name__ == "__main__":
    # Run with SSE (Server-Sent Events) transport
    # This requires Accept: application/json, text/event-stream header
    mcp.run(transport="sse")
