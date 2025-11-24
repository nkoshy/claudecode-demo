#!/usr/bin/env python3
"""
Test if FastMCP accepts nullable objects, arrays, integers, etc.
"""

import json
from fastmcp import FastMCP
import httpx

# Test schema with various nullable types
test_spec = {
    "openapi": "3.0.0",
    "info": {"title": "Test", "version": "1.0.0"},
    "servers": [{"url": "https://example.com"}],
    "paths": {
        "/test": {
            "get": {
                "operationId": "testNullableTypes",
                "responses": {
                    "200": {
                        "description": "Test response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "nullable": True,  # Nullable object
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "nullable": True
                                        },
                                        "count": {
                                            "type": "integer",
                                            "nullable": True  # Nullable integer
                                        },
                                        "active": {
                                            "type": "boolean",
                                            "nullable": True  # Nullable boolean
                                        },
                                        "tags": {
                                            "type": "array",
                                            "nullable": True,  # Nullable array
                                            "items": {
                                                "type": "string",
                                                "nullable": True
                                            }
                                        },
                                        "metadata": {
                                            "type": "object",
                                            "nullable": True,  # Nested nullable object
                                            "properties": {
                                                "value": {
                                                    "type": "string",
                                                    "nullable": True
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

try:
    print("Testing FastMCP with nullable objects, arrays, integers, booleans...")
    client = httpx.AsyncClient()

    # Try to create FastMCP server with nullable types
    mcp = FastMCP.from_openapi(test_spec, client, name="test")

    print("✅ SUCCESS! FastMCP accepts:")
    print("   - nullable objects")
    print("   - nullable arrays")
    print("   - nullable integers")
    print("   - nullable booleans")
    print("   - nullable strings")
    print("\nThe ultra-aggressive mode fixes should work correctly!")

except Exception as e:
    print(f"❌ FAILED: {type(e).__name__}: {str(e)}")
    print("\nThis means we need a different approach...")
    import traceback
    traceback.print_exc()
