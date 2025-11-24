#!/usr/bin/env python3
"""
Kubernetes OpenAPI schema fixer for FastMCP.

FastMCP requires strict OpenAPI 3.0 format where:
- type must be a single string, not an array
- nullable fields use `nullable: true` property instead of type arrays

Usage:
  python k8s_openapi_fastmcp_fix.py \
      --spec core-v1-openapi.json \
      --spec apps-v1-openapi.json \
      --spec networking-v1-openapi.json \
      --output-dir fastmcp-fixed-specs

  Optional: --aggressive to make ALL fields nullable (strings, integers, booleans, objects, arrays)
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

Json = Any

# Target resource paths to fix
TARGET_BASE_PATHS = [
    "/api/v1/namespaces/{namespace}/pods",
    "/api/v1/namespaces/{namespace}/services",
    "/api/v1/namespaces/{namespace}/configmaps",
    "/api/v1/namespaces/{namespace}/secrets",
    "/apis/apps/v1/namespaces/{namespace}/deployments",
    "/apis/apps/v1/namespaces/{namespace}/replicasets",
    "/apis/apps/v1/namespaces/{namespace}/statefulsets",
    "/apis/apps/v1/namespaces/{namespace}/daemonsets",
    "/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses",
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def is_target_path(path: str) -> bool:
    """Check if a path should be included in the filtered output."""
    for tmpl in TARGET_BASE_PATHS:
        base = tmpl
        if path == base or path.startswith(base + "/"):
            return True
    return False


def fix_type_array_to_nullable(schema: Json, path: str = "", aggressive: bool = False) -> int:
    """
    Convert type arrays like ['string', 'null'] to type: 'string' with nullable: true.
    This is required for FastMCP compatibility.
    Returns count of fixes applied.
    """
    fixes = 0

    if not isinstance(schema, dict):
        return fixes

    # Remove empty required arrays (FastMCP requires at least 1 item)
    if "required" in schema and isinstance(schema["required"], list) and len(schema["required"]) == 0:
        del schema["required"]
        log(f"[FIX] {path}: removed empty required array")
        fixes += 1

    # Fix type arrays
    if "type" in schema:
        type_val = schema["type"]

        # If type is a list containing 'null', convert to nullable
        if isinstance(type_val, list):
            non_null_types = [t for t in type_val if t != "null"]
            has_null = "null" in type_val

            if has_null and len(non_null_types) == 1:
                # Convert ['string', 'null'] to type: 'string', nullable: true
                schema["type"] = non_null_types[0]
                schema["nullable"] = True
                log(f"[FIX] {path}: converted type {type_val} to type '{non_null_types[0]}' with nullable=true")
                fixes += 1
            elif has_null and len(non_null_types) > 1:
                # Multiple non-null types with null - use anyOf
                schema.pop("type")
                schema["anyOf"] = [{"type": t} for t in non_null_types] + [{"type": "null"}]
                log(f"[FIX] {path}: converted type {type_val} to anyOf with nullable")
                fixes += 1
            elif len(type_val) == 1:
                # Single type in array - just use the type directly
                schema["type"] = type_val[0]
                log(f"[FIX] {path}: unwrapped single-element type array {type_val}")
                fixes += 1

    # Aggressive mode: make ALL typed fields nullable (not just strings)
    # Kubernetes can return null for any field: strings, integers, booleans, objects, arrays, numbers
    if aggressive and "type" in schema and not schema.get("nullable"):
        field_type = schema["type"]
        # Only add nullable if it's a simple type (not already an array/object with complex validation)
        if isinstance(field_type, str):
            schema["nullable"] = True
            log(f"[FIX] {path}: made {field_type} field nullable (aggressive mode)")
            fixes += 1

    # Recurse into common schema locations
    if "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            if isinstance(prop_schema, dict):
                fixes += fix_type_array_to_nullable(prop_schema, f"{path}.{prop_name}", aggressive)

    for key in ["items", "additionalProperties"]:
        if key in schema and isinstance(schema[key], dict):
            fixes += fix_type_array_to_nullable(schema[key], f"{path}.{key}", aggressive)

    if "allOf" in schema:
        for i, sub_schema in enumerate(schema["allOf"]):
            if isinstance(sub_schema, dict):
                fixes += fix_type_array_to_nullable(sub_schema, f"{path}.allOf[{i}]", aggressive)

    if "oneOf" in schema:
        for i, sub_schema in enumerate(schema["oneOf"]):
            if isinstance(sub_schema, dict):
                fixes += fix_type_array_to_nullable(sub_schema, f"{path}.oneOf[{i}]", aggressive)

    if "anyOf" in schema:
        for i, sub_schema in enumerate(schema["anyOf"]):
            if isinstance(sub_schema, dict):
                fixes += fix_type_array_to_nullable(sub_schema, f"{path}.anyOf[{i}]", aggressive)

    return fixes


def get_response_schema(operation: Dict[str, Any]) -> Json:
    """Extract the response schema from an operation."""
    responses = operation.get("responses", {})
    for code in ["200", "201", "202"]:
        if code in responses:
            resp_obj = responses[code]
            content = resp_obj.get("content", {})
            app_json = content.get("application/json", {})
            if "schema" in app_json:
                return app_json["schema"]
    if "default" in responses:
        resp_obj = responses["default"]
        content = resp_obj.get("content", {})
        app_json = content.get("application/json", {})
        if "schema" in app_json:
            return app_json["schema"]
    return None


def get_request_body_schema(operation: Dict[str, Any]) -> Json:
    """Extract the request body schema from an operation."""
    rb = operation.get("requestBody", {})
    content = rb.get("content", {})
    app_json = content.get("application/json", {})
    return app_json.get("schema")


def filter_and_fix_spec(spec: Json, spec_name: str, aggressive: bool = False) -> tuple[Json, int]:
    """
    Filter spec to only target paths and apply FastMCP-compatible fixes.
    Returns (filtered_spec, fix_count)
    """
    log(f"\nProcessing {spec_name}...")

    filtered_spec = {
        "openapi": spec.get("openapi", "3.0.0"),
        "info": spec.get("info", {}),
        "paths": {},
        "components": spec.get("components", {}),
    }

    # Filter paths
    original_path_count = len(spec.get("paths", {}))
    for path, path_item in spec.get("paths", {}).items():
        if is_target_path(path):
            filtered_spec["paths"][path] = path_item

    filtered_path_count = len(filtered_spec["paths"])
    log(f"  Filtered paths: {filtered_path_count}/{original_path_count}")

    # Apply fixes to the entire spec
    total_fixes = 0

    # Fix components/schemas
    if "components" in filtered_spec and "schemas" in filtered_spec["components"]:
        log(f"  Fixing component schemas...")
        for schema_name, schema in filtered_spec["components"]["schemas"].items():
            fixes = fix_type_array_to_nullable(schema, f"components.schemas.{schema_name}", aggressive)
            total_fixes += fixes

    # Fix inline schemas in operations
    log(f"  Fixing operation schemas...")
    for path, path_item in filtered_spec.get("paths", {}).items():
        for method in ["get", "post", "put", "patch", "delete"]:
            if method in path_item:
                operation = path_item[method]

                # Fix response schemas
                resp_schema = get_response_schema(operation)
                if resp_schema:
                    fixes = fix_type_array_to_nullable(resp_schema, f"{path}.{method}.response", aggressive)
                    total_fixes += fixes

                # Fix request body schemas
                req_schema = get_request_body_schema(operation)
                if req_schema:
                    fixes = fix_type_array_to_nullable(req_schema, f"{path}.{method}.requestBody", aggressive)
                    total_fixes += fixes

    log(f"  Total fixes applied: {total_fixes}")
    return filtered_spec, total_fixes


def main():
    parser = argparse.ArgumentParser(
        description="Filter and fix Kubernetes OpenAPI specs for FastMCP compatibility."
    )
    parser.add_argument(
        "--spec",
        action="append",
        dest="specs",
        required=True,
        help="Path to a Kubernetes OpenAPI v3 JSON file (repeatable).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write fixed spec JSON files.",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Make ALL fields nullable - strings, integers, booleans, objects, arrays (recommended for K8s which can return null for any field)",
    )

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    total_fixes = 0

    for spec_path in args.specs:
        spec_name = os.path.basename(spec_path)

        # Load spec
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)

        # Filter and fix
        fixed_spec, fixes = filter_and_fix_spec(spec, spec_name, args.aggressive)
        total_fixes += fixes

        # Write output
        out_path = os.path.join(args.output_dir, spec_name)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fixed_spec, f, indent=2, ensure_ascii=False)

        log(f"  Wrote: {out_path}\n")

    log(f"\n{'='*60}")
    log(f"SUMMARY: Applied {total_fixes} fixes across all specs")
    log(f"{'='*60}")


if __name__ == "__main__":
    main()
