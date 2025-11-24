#!/usr/bin/env python3
"""
Merge and filter OpenAPI specs to include only specific namespace-scoped operations.
"""

import json
import sys
from typing import Dict, Any, Set

# Target operations we want to keep
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

def collect_schema_refs(obj: Any, refs: Set[str]):
    """Recursively collect all $ref references in an object."""
    if isinstance(obj, dict):
        if "$ref" in obj:
            ref = obj["$ref"]
            if ref.startswith("#/components/schemas/"):
                schema_name = ref.replace("#/components/schemas/", "")
                refs.add(schema_name)
        for value in obj.values():
            collect_schema_refs(value, refs)
    elif isinstance(obj, list):
        for item in obj:
            collect_schema_refs(item, refs)

def collect_referenced_schemas(schemas: Dict[str, Any], initial_refs: Set[str]) -> Dict[str, Any]:
    """Recursively collect all schemas referenced by the initial set."""
    collected = {}
    to_process = list(initial_refs)
    processed = set()

    while to_process:
        schema_name = to_process.pop()
        if schema_name in processed or schema_name not in schemas:
            continue

        processed.add(schema_name)
        schema = schemas[schema_name]
        collected[schema_name] = schema

        # Find references in this schema
        refs = set()
        collect_schema_refs(schema, refs)
        to_process.extend(refs - processed)

    return collected

def filter_paths(spec: Dict[str, Any], target_paths: list) -> tuple[Dict[str, Any], Set[str]]:
    """Filter paths to only include target paths and collect schema references."""
    filtered_paths = {}
    schema_refs = set()

    for path in spec.get("paths", {}):
        # Check if this path or any of its subpaths should be included
        should_include = False
        for target_path in target_paths:
            if path == target_path or path.startswith(target_path + "/"):
                should_include = True
                break

        if should_include:
            filtered_paths[path] = spec["paths"][path]
            # Collect schema references from this path
            collect_schema_refs(spec["paths"][path], schema_refs)

    return filtered_paths, schema_refs

def merge_specs(spec_files: list, target_paths: list, output_file: str):
    """Merge multiple OpenAPI specs, filtering to only target paths."""

    # Start with a base structure
    merged = {
        "openapi": "3.0.0",
        "info": {
            "title": "Kubernetes Namespace-Scoped API (Filtered)",
            "version": "v1",
            "description": "Filtered Kubernetes API containing only namespace-scoped operations for Pods, Services, ConfigMaps, Secrets, Deployments, ReplicaSets, StatefulSets, DaemonSets, and Ingresses."
        },
        "servers": [
            {
                "url": "https://kubernetes.default.svc",
                "description": "Kubernetes API Server"
            }
        ],
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {
                "BearerToken": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Kubernetes service account token"
                }
            }
        },
        "security": [
            {"BearerToken": []}
        ]
    }

    all_schema_refs = set()

    # Process each spec file
    for spec_file in spec_files:
        print(f"Processing {spec_file}...")
        with open(spec_file) as f:
            spec = json.load(f)

        # Filter paths and collect schema references
        filtered_paths, schema_refs = filter_paths(spec, target_paths)

        # Merge paths
        merged["paths"].update(filtered_paths)
        all_schema_refs.update(schema_refs)

        print(f"  Added {len(filtered_paths)} paths")

    # Collect all referenced schemas from all spec files
    print("\nCollecting referenced schemas...")
    all_schemas = {}
    for spec_file in spec_files:
        with open(spec_file) as f:
            spec = json.load(f)
        if "components" in spec and "schemas" in spec["components"]:
            all_schemas.update(spec["components"]["schemas"])

    # Recursively collect all schemas that are referenced
    merged["components"]["schemas"] = collect_referenced_schemas(all_schemas, all_schema_refs)
    print(f"  Collected {len(merged['components']['schemas'])} schemas")

    # Write merged spec
    with open(output_file, "w") as f:
        json.dump(merged, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Merged OpenAPI Spec: {output_file}")
    print(f"{'='*60}")
    print(f"Total paths: {len(merged['paths'])}")
    print(f"Total schemas: {len(merged['components']['schemas'])}")
    print(f"\nPaths included:")
    for path in sorted(merged["paths"].keys()):
        methods = [m for m in merged["paths"][path].keys() if m != "parameters"]
        print(f"  {path}")
        print(f"    Methods: {', '.join(methods)}")

    # Count operations
    total_ops = 0
    for path_item in merged["paths"].values():
        total_ops += len([m for m in path_item.keys() if m != "parameters"])
    print(f"\nTotal operations: {total_ops}")

if __name__ == "__main__":
    spec_files = [
        "fastmcp-fixed-specs/core-v1-openapi.json",
        "fastmcp-fixed-specs/apps-v1-openapi.json",
        "fastmcp-fixed-specs/networking-v1-openapi.json"
    ]

    output_file = "fastmcp-fixed-specs/k8s-namespace-ops-merged.json"

    print("Merging and filtering Kubernetes OpenAPI specs...")
    print(f"Target operations: {len(TARGET_BASE_PATHS)}")
    print()

    merge_specs(spec_files, TARGET_BASE_PATHS, output_file)

    print(f"\n✅ Done! Merged spec written to: {output_file}")
