# Kubernetes FastMCP Server with Fixed Schemas

This example shows how to deploy a FastMCP server for Kubernetes that uses the **aggressive mode fixed schemas** to handle null values in API responses.

## The Problem

Kubernetes can return `null` for many string fields, causing validation errors like:
```
Output validation error: None is not of type 'string'
```

## The Solution

Use the **aggressive mode fixed specs** from `fastmcp-fixed-specs/` which have **989 fixes applied** making all string fields nullable.

## Files Needed

1. **server.py** - Your FastMCP server code
2. **requirements.txt** - Python dependencies
3. **Dockerfile** - Container build instructions
4. **fastmcp-fixed-specs/** - The FIXED OpenAPI specs (MUST include!)
   - core-v1-openapi.json
   - apps-v1-openapi.json
   - networking-v1-openapi.json

## How to Build

```bash
# 1. Generate the aggressive mode fixed specs (if not already done)
python k8s_openapi_fastmcp_fix.py \
  --spec core-v1-openapi.json \
  --spec apps-v1-openapi.json \
  --spec networking-v1-openapi.json \
  --output-dir fastmcp-fixed-specs \
  --aggressive

# 2. Copy the fixed specs to your server directory
cp -r fastmcp-fixed-specs/ example-mcp-server/

# 3. Build the Docker image
cd example-mcp-server
docker build -t k8s-mcp-server:latest .

# 4. Run locally to test
docker run -p 8000:8000 \
  -e K8S_API_SERVER="https://your-cluster" \
  -e K8S_TOKEN="your-token" \
  k8s-mcp-server:latest
```

## Deploy to Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-mcp-server
  namespace: devnamespace
spec:
  replicas: 1
  selector:
    matchLabels:
      app: k8s-mcp-server
  template:
    metadata:
      labels:
        app: k8s-mcp-server
    spec:
      serviceAccountName: devsa  # Your service account with K8s API access
      containers:
      - name: server
        image: k8s-mcp-server:latest
        ports:
        - containerPort: 8000
        env:
        - name: K8S_API_SERVER
          value: "https://kubernetes.default.svc"
        - name: K8S_TOKEN
          valueFrom:
            secretKeyRef:
              name: devsa-token
              key: token
---
apiVersion: v1
kind: Service
metadata:
  name: k8s-mcp-server
  namespace: devnamespace
spec:
  selector:
    app: k8s-mcp-server
  ports:
  - port: 80
    targetPort: 8000
```

## Verify It Works

Test the deployment tool:
```bash
# Should work without "None is not of type 'string'" errors
curl https://your-server/tools/listAppsV1NamespacedDeployment \
  -d '{"namespace": "devnamespace"}'
```

## What Changed?

The aggressive mode fixed specs have:
- **989 fixes total**
- ALL string fields now have `nullable: true`
- Empty `required` arrays removed
- Full FastMCP compatibility

This completely eliminates validation errors from null values in Kubernetes responses.
