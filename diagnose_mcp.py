#!/usr/bin/env python3
"""
Quick diagnostic to see what's failing with tools/list
"""

import asyncio
import httpx
import json

async def diagnose():
    url = "https://k8smcp.k8smcp.cloud/mcp"
    client = httpx.AsyncClient(timeout=30.0)

    print("="*60)
    print("MCP Server Diagnostic")
    print("="*60)

    # Step 1: Initialize
    print("\n1. Sending initialize...")
    init_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "diagnostic", "version": "1.0"}
        }
    }

    resp1 = await client.post(url, json=init_msg, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    })

    print(f"   Status: {resp1.status_code}")
    print(f"   Response: {resp1.text[:300]}")

    # Step 2: Send initialized notification
    print("\n2. Sending notifications/initialized...")
    notif_msg = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }

    resp2 = await client.post(url, json=notif_msg, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    })

    print(f"   Status: {resp2.status_code}")
    print(f"   Response: {resp2.text if resp2.text else '(no response - expected for notification)'}")

    # Step 3: List tools
    print("\n3. Sending tools/list...")
    tools_msg = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }

    resp3 = await client.post(url, json=tools_msg, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    })

    print(f"   Status: {resp3.status_code}")
    if resp3.status_code >= 400:
        print(f"   ❌ ERROR Response: {resp3.text}")
    else:
        print(f"   ✅ Response: {resp3.text[:300]}")

    await client.aclose()

if __name__ == "__main__":
    asyncio.run(diagnose())
