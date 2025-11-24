#!/usr/bin/env python3
"""
Offline Kubernetes OpenAPI schema fixer.

Filters OpenAPI specs to target paths and applies common fixes:
- Allows null for optional fields (type: "string" -> type: ["string", "null"])
- Removes commonly missing fields from required arrays
- Fixes known Kubernetes schema issues

Usage:
  python k8s_openapi_offline_fix.py \
      --spec core-v1-openapi.json \
      --spec apps-v1-openapi.json \
      --spec networking-v1-openapi.json \
      --output-dir fixed-specs
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Set

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

# Fields that are commonly null in Kubernetes but defined as string
NULLABLE_STRING_FIELDS = {
    "lastTransitionTime",
    "message",
    "reason",
    "creationTimestamp",
    "deletionTimestamp",
    "resourceVersion",
    "selfLink",
    "uid",
    "apiVersion",
    "kind",
    "finalizers",
    "generateName",
    "managedFields",
    "ownerReferences",
    "clusterName",
    "namespace",
    "annotations",
    "labels",
}

# Fields commonly missing from required arrays
OPTIONAL_FIELDS = {
    "status",
    "metadata",
    "annotations",
    "labels",
    "finalizers",
    "ownerReferences",
    "managedFields",
    "resourceVersion",
    "selfLink",
    "uid",
    "creationTimestamp",
    "deletionTimestamp",
    "deletionGracePeriodSeconds",
    "clusterName",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def is_target_path(path: str) -> bool:
    """Check if a path should be included in the filtered output."""
    for tmpl in TARGET_BASE_PATHS:
        base = tmpl
        if path == base or path.startswith(base + "/"):
            return True
    return False


def fix_null_types(schema: Json, path: str = "") -> int:
    """
    Recursively fix type definitions to allow null where appropriate.
    Returns count of fixes applied.
    """
    fixes = 0

    if not isinstance(schema, dict):
        return fixes

    # Fix type: "string" to allow null for known nullable fields
    if "type" in schema and "properties" in schema:
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if isinstance(prop_schema, dict):
                prop_type = prop_schema.get("type")

                # If it's a string type and the field name is in our nullable list
                if prop_type == "string" and prop_name in NULLABLE_STRING_FIELDS:
                    prop_schema["type"] = ["string", "null"]
                    prop_schema.pop("nullable", None)  # Remove deprecated nullable
                    log(f"[FIX] {path}.{prop_name}: allowed null for string type")
                    fixes += 1

                # Recurse into nested schemas
                fixes += fix_null_types(prop_schema, f"{path}.{prop_name}")

    # Also check if this schema itself is a string that should allow null
    if schema.get("type") == "string":
        # Check the parent context - if we're in a property that's commonly null
        last_part = path.split(".")[-1] if "." in path else path
        if last_part in NULLABLE_STRING_FIELDS:
            schema["type"] = ["string", "null"]
            schema.pop("nullable", None)
            log(f"[FIX] {path}: allowed null for string type")
            fixes += 1

    # Recurse into common schema locations
    for key in ["items", "additionalProperties"]:
        if key in schema:
            fixes += fix_null_types(schema[key], f"{path}.{key}")

    if "allOf" in schema:
        for i, sub_schema in enumerate(schema["allOf"]):
            fixes += fix_null_types(sub_schema, f"{path}.allOf[{i}]")

    if "oneOf" in schema:
        for i, sub_schema in enumerate(schema["oneOf"]):
            fixes += fix_null_types(sub_schema, f"{path}.oneOf[{i}]")

    if "anyOf" in schema:
        for i, sub_schema in enumerate(schema["anyOf"]):
            fixes += fix_null_types(sub_schema, f"{path}.anyOf[{i}]")

    return fixes


def fix_required_fields(schema: Json, path: str = "") -> int:
    """
    Remove commonly optional fields from required arrays.
    Returns count of fixes applied.
    """
    fixes = 0

    if not isinstance(schema, dict):
        return fixes

    # Fix required arrays
    if "required" in schema and isinstance(schema["required"], list):
        original_required = schema["required"][:]
        schema["required"] = [
            field for field in schema["required"]
            if field not in OPTIONAL_FIELDS
        ]

        removed = set(original_required) - set(schema["required"])
        if removed:
            log(f"[FIX] {path}: removed optional fields from required: {removed}")
            fixes += len(removed)

    # Recurse
    if "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            if isinstance(prop_schema, dict):
                fixes += fix_required_fields(prop_schema, f"{path}.{prop_name}")

    for key in ["items", "additionalProperties"]:
        if key in schema:
            fixes += fix_required_fields(schema[key], f"{path}.{key}")

    if "allOf" in schema:
        for i, sub_schema in enumerate(schema["allOf"]):
            fixes += fix_required_fields(sub_schema, f"{path}.allOf[{i}]")

    if "oneOf" in schema:
        for i, sub_schema in enumerate(schema["oneOf"]):
            fixes += fix_required_fields(sub_schema, f"{path}.oneOf[{i}]")

    if "anyOf" in schema:
        for i, sub_schema in enumerate(schema["anyOf"]):
            fixes += fix_required_fields(sub_schema, f"{path}.anyOf[{i}]")

    return fixes


def get_response_schema(operation: Dict[str, Any]) -> Json:
    """Extract the response schema from an operation."""
    responses = operation.get("responses", {})

    # Try 200, 201, 202, or default
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


def filter_and_fix_spec(spec: Json, spec_name: str) -> tuple[Json, int]:
    """
    Filter spec to only target paths and apply fixes.
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

    # Apply fixes to the entire spec (including components which contain shared schemas)
    total_fixes = 0

    # Fix components/schemas
    if "components" in filtered_spec and "schemas" in filtered_spec["components"]:
        log(f"  Fixing component schemas...")
        for schema_name, schema in filtered_spec["components"]["schemas"].items():
            fixes = fix_null_types(schema, f"components.schemas.{schema_name}")
            fixes += fix_required_fields(schema, f"components.schemas.{schema_name}")
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
                    fixes = fix_null_types(resp_schema, f"{path}.{method}.response")
                    fixes += fix_required_fields(resp_schema, f"{path}.{method}.response")
                    total_fixes += fixes

                # Fix request body schemas
                req_schema = get_request_body_schema(operation)
                if req_schema:
                    fixes = fix_null_types(req_schema, f"{path}.{method}.requestBody")
                    fixes += fix_required_fields(req_schema, f"{path}.{method}.requestBody")
                    total_fixes += fixes

    log(f"  Total fixes applied: {total_fixes}")
    return filtered_spec, total_fixes


def main():
    parser = argparse.ArgumentParser(
        description="Filter and fix Kubernetes OpenAPI specs offline."
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

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    total_fixes = 0

    for spec_path in args.specs:
        spec_name = os.path.basename(spec_path)

        # Load spec
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)

        # Filter and fix
        fixed_spec, fixes = filter_and_fix_spec(spec, spec_name)
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
