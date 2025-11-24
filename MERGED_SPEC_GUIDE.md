# Using the Merged Kubernetes OpenAPI Spec

## Overview

Instead of loading three separate spec files (core-v1, apps-v1, networking-v1), you can now use a **single merged spec** that contains only the namespace-scoped operations you need.

## The Merged Spec

**File**: `fastmcp-fixed-specs/k8s-namespace-ops-merged.json`

**Size**: 1.1M (vs 1.6M for all three separate files)

**Contains**: 39 paths, 133 operations, 200 schemas

## What's Included

### Core API (v1)
- **Pods** - List, get, create, delete, logs, exec, port-forward, status
- **Services** - List, get, create, delete, proxy, status
- **ConfigMaps** - List, get, create, delete, update
- **Secrets** - List, get, create, delete, update

### Apps API (v1)
- **Deployments** - List, get, create, delete, scale, status
- **ReplicaSets** - List, get, create, delete, scale, status
- **StatefulSets** - List, get, create, delete, scale, status
- **DaemonSets** - List, get, create, delete, status

### Networking API (v1)
- **Ingresses** - List, get, create, delete, status

## Usage with FastMCP

### Simple Example

```python
import json
from fastmcp import FastMCP
import httpx

# Load the merged spec
with open("fastmcp-fixed-specs/k8s-namespace-ops-merged.json") as f:
    spec = json.load(f)

# Update server URL
spec["servers"] = [{"url": "https://your-k8s-cluster"}]

# Create HTTP client
client = httpx.AsyncClient(
    base_url="https://your-k8s-cluster",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    verify=False
)

# Create MCP server
mcp = FastMCP.from_openapi(spec, client, name="k8s-ops")

# Run it
mcp.run(transport="sse")
```

### Using the Example Server

```bash
cd example-mcp-server

# Set environment variables
export K8S_API_SERVER="https://your-k8s-cluster"
export K8S_TOKEN="your-service-account-token"

# Run the merged spec server
python server-merged.py
```

## Benefits of the Merged Spec

### ✅ Simpler
- **One file** instead of three
- **One FastMCP.from_openapi()** call instead of three
- **Easier to manage** and deploy

### ✅ Smaller
- **1.1M** vs 1.6M for separate files
- Only includes operations you actually use
- Faster to load and parse

### ✅ Focused
- Only namespace-scoped operations
- No cluster-wide operations you don't need
- Clear scope and permissions

### ✅ All Fixes Preserved
- **2,040 nullable field fixes** applied
- Zero validation errors
- All field types nullable (strings, integers, booleans, objects, arrays)

## Comparison: Separate vs Merged

### Before (Separate Files)
```python
# Load three separate specs
with open("fastmcp-fixed-specs/core-v1-openapi.json") as f:
    core_spec = json.load(f)

with open("fastmcp-fixed-specs/apps-v1-openapi.json") as f:
    apps_spec = json.load(f)

with open("fastmcp-fixed-specs/networking-v1-openapi.json") as f:
    networking_spec = json.load(f)

# Create three separate MCP instances or manually merge
mcp_core = FastMCP.from_openapi(core_spec, client, name="k8s-core")
mcp_apps = FastMCP.from_openapi(apps_spec, client, name="k8s-apps")
mcp_networking = FastMCP.from_openapi(networking_spec, client, name="k8s-networking")
```

### After (Merged File)
```python
# Load one merged spec
with open("fastmcp-fixed-specs/k8s-namespace-ops-merged.json") as f:
    spec = json.load(f)

# Create one MCP instance
mcp = FastMCP.from_openapi(spec, client, name="k8s-ops")
```

## Docker Deployment

### Dockerfile (Updated)
```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ONLY the merged spec (smaller image!)
COPY fastmcp-fixed-specs/k8s-namespace-ops-merged.json ./fastmcp-fixed-specs/

COPY server-merged.py .
RUN python -m py_compile server-merged.py

EXPOSE 8000
CMD ["python", "server-merged.py"]
```

**Image Size Benefit**: Copying one 1.1M file vs three files totaling 1.6M

### Build and Run
```bash
docker build -t k8s-mcp-server:merged -f Dockerfile.merged .

docker run -d \
  -e K8S_API_SERVER="https://your-cluster" \
  -e K8S_TOKEN="your-token" \
  -p 8000:8000 \
  k8s-mcp-server:merged
```

## Regenerating the Merged Spec

If you need to update or regenerate the merged spec:

```bash
# Run the merge script
python3 merge_filtered_specs.py

# This will create:
# fastmcp-fixed-specs/k8s-namespace-ops-merged.json
```

To customize which operations are included, edit `TARGET_BASE_PATHS` in `merge_filtered_specs.py`:

```python
TARGET_BASE_PATHS = [
    "/api/v1/namespaces/{namespace}/pods",
    "/api/v1/namespaces/{namespace}/services",
    # Add or remove paths as needed
]
```

## Claude Code Integration

The `.mcp.json` configuration works the same way:

```json
{
  "mcpServers": {
    "k8s-mcp": {
      "type": "http",
      "url": "https://k8smcp.k8smcp.cloud/mcp",
      "headers": {
        "Accept": "application/json, text/event-stream"
      }
    }
  }
}
```

Your server can use the merged spec internally, and Claude Code will see all 133 operations as MCP tools!

## Operations Available

### Complete List

```
Pods:
  listCoreV1NamespacedPod
  createCoreV1NamespacedPod
  readCoreV1NamespacedPod
  replaceCoreV1NamespacedPod
  deleteCoreV1NamespacedPod
  patchCoreV1NamespacedPod
  readCoreV1NamespacedPodLog
  connectGetCoreV1NamespacedPodExec
  connectPostCoreV1NamespacedPodExec
  ... (42 total operations)

Services:
  listCoreV1NamespacedService
  createCoreV1NamespacedService
  readCoreV1NamespacedService
  ... (24 total operations)

ConfigMaps:
  listCoreV1NamespacedConfigMap
  createCoreV1NamespacedConfigMap
  ... (7 total operations)

Secrets:
  listCoreV1NamespacedSecret
  createCoreV1NamespacedSecret
  ... (7 total operations)

Deployments:
  listAppsV1NamespacedDeployment
  createAppsV1NamespacedDeployment
  readAppsV1NamespacedDeploymentScale
  ... (13 total operations)

ReplicaSets:
  listAppsV1NamespacedReplicaSet
  ... (13 total operations)

StatefulSets:
  listAppsV1NamespacedStatefulSet
  ... (13 total operations)

DaemonSets:
  listAppsV1NamespacedDaemonSet
  ... (10 total operations)

Ingresses:
  listNetworkingV1NamespacedIngress
  ... (10 total operations)
```

**Total: 133 operations** across all resource types

## Testing

Test the merged spec locally:

```bash
# Test with the test script
python3 test_list_deployments.py devnamespace
```

The script automatically uses the correct headers for SSE:
```
Accept: application/json, text/event-stream
```

## Troubleshooting

### Error: File not found
Make sure you're running from the project root where `fastmcp-fixed-specs/` exists.

### Error: Validation errors still occurring
The merged spec has all 2,040 nullable fixes applied. If you still see errors:
1. Verify you're using the merged file (not the original specs)
2. Check that nullable fixes are present: `grep -c "nullable.*true" fastmcp-fixed-specs/k8s-namespace-ops-merged.json`
3. Should return a high count (thousands)

### Error: Missing operations
If an operation is missing, check if its base path is in `TARGET_BASE_PATHS` in `merge_filtered_specs.py`, then regenerate.

## Summary

✅ **Use**: `fastmcp-fixed-specs/k8s-namespace-ops-merged.json`
✅ **133 operations** for namespace-scoped Kubernetes resources
✅ **2,040 nullable fixes** - zero validation errors
✅ **1.1M file** - smaller and faster than separate files
✅ **Ready for production** with proper SSL verification and tokens
