# MCP Server Setup Guide for Claude Code

## ✅ Configuration Created

The `.mcp.json` file has been created in your project root with your Kubernetes MCP server configuration.

## 🔑 Step 1: Set Your Authentication Token

You need to set the `K8S_MCP_TOKEN` environment variable with your authentication token.

### Option A: Set for Current Session
```bash
export K8S_MCP_TOKEN="your-actual-authentication-token"
```

### Option B: Add to Your Shell Profile (Persistent)
Add to `~/.bashrc`, `~/.zshrc`, or `~/.profile`:
```bash
export K8S_MCP_TOKEN="your-actual-authentication-token"
```

Then reload:
```bash
source ~/.bashrc  # or ~/.zshrc
```

### Option C: Use Project .env File
Create a `.env` file in your project:
```bash
echo "K8S_MCP_TOKEN=your-actual-authentication-token" > .env
```

Then load it before starting Claude Code:
```bash
source .env
claude
```

## 🧪 Step 2: Verify the Connection

### Test with Debug Mode
```bash
claude --mcp-debug
```

This will show:
- ✓ Connection attempt to your MCP server
- ✓ Available tools discovered from the server
- ✗ Any authentication or connection errors

### Test with a Simple Command
Once connected, try asking me:
- "List pods in the devnamespace namespace"
- "Show all deployments in devnamespace"
- "Get the status of pods in devnamespace"

I'll automatically use the MCP server tools to execute these operations!

## 📋 What You Get

Once configured, I'll have access to **133 Kubernetes API endpoints** across:

**core-v1 (74 endpoints)**:
- Pods, Services, ConfigMaps, Secrets, PersistentVolumes, etc.
- Example: `listCoreV1NamespacedPod` - list pods in a namespace

**apps-v1 (49 endpoints)**:
- Deployments, StatefulSets, DaemonSets, ReplicaSets
- Example: `listAppsV1NamespacedDeployment` - list deployments

**networking-v1 (10 endpoints)**:
- Ingress, NetworkPolicy, IngressClass
- Example: `listNetworkingV1NamespacedIngress` - list ingress resources

## 🔍 View Available Tools

Once connected, you can ask me to:
- List all available Kubernetes operations
- Show details about specific resources
- Execute any supported K8s API operation

## 🚨 Troubleshooting

### Error: "Access denied" or 403
- Verify your `K8S_MCP_TOKEN` is set correctly
- Check the token has proper permissions
- Test with curl:
  ```bash
  curl -H "Authorization: Bearer $K8S_MCP_TOKEN" \
       -H "Content-Type: application/json" \
       -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
       https://k8smcp.k8smcp.cloud/mcp
  ```

### Server Not Connecting
1. Verify the URL is accessible: `curl https://k8smcp.k8smcp.cloud/mcp`
2. Check environment variable is set: `echo $K8S_MCP_TOKEN`
3. Run with debug flag: `claude --mcp-debug`

### Tools Not Appearing
- Restart Claude Code after setting environment variables
- Check `.mcp.json` is in the project root (same level as `.claude/`)
- Verify JSON syntax is valid: `jq . .mcp.json`

## 📁 Project Structure

Your project now has:
```
/home/user/claudecode-demo/
├── .claude/
│   ├── settings.json           # Existing: permissions & hooks
│   └── stop-hook-git-check.sh  # Existing: git validation hook
├── .mcp.json                    # NEW: MCP server configuration
├── fastmcp-fixed-specs/         # Fixed OpenAPI schemas (2,040 fixes)
├── example-mcp-server/          # Example deployment
└── [other project files...]
```

## 🎯 Benefits

With the MCP server connected and the **ultra-aggressive fixes** (2,040 nullable fields):

✓ **No more validation errors** - All field types are nullable
✓ **Direct K8s access** - I can query your cluster in real-time
✓ **133 API operations** - Full control over pods, deployments, services, etc.
✓ **Namespace-scoped** - Safe operations within your designated namespaces

## 🔐 Security Notes

- ✓ `.mcp.json` is safe to commit (no secrets, just configuration)
- ✗ Never commit `.env` or tokens to git
- ✓ Use environment variables for all credentials
- ✓ The token should have minimal required permissions (namespace-scoped)

## Next Steps

1. Set your `K8S_MCP_TOKEN` environment variable
2. Run `claude --mcp-debug` to verify connection
3. Ask me to list pods or deployments to test!
