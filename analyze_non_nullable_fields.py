#!/usr/bin/env python3
"""
Analyze fixed schemas to find non-string fields that aren't marked as nullable.
These could be causing validation errors when Kubernetes returns null.
"""

import json
from collections import defaultdict

def find_non_nullable_fields(schema, path="", type_counts=None):
    """Recursively find fields that have types but aren't nullable."""
    if type_counts is None:
        type_counts = defaultdict(int)

    if not isinstance(schema, dict):
        return type_counts

    # Check if this schema has a non-nullable type
    if "type" in schema:
        field_type = schema["type"]
        is_nullable = schema.get("nullable", False)

        if not is_nullable and field_type != "string":
            type_counts[field_type] += 1
            if type_counts[field_type] <= 3:  # Show first 3 examples
                print(f"  {path}: type={field_type}, nullable={is_nullable}")

    # Recurse
    for key in ["properties", "additionalProperties", "items"]:
        if key in schema:
            if key == "properties" and isinstance(schema[key], dict):
                for prop_name, prop_schema in schema[key].items():
                    find_non_nullable_fields(prop_schema, f"{path}.{prop_name}", type_counts)
            elif isinstance(schema[key], dict):
                find_non_nullable_fields(schema[key], f"{path}.{key}", type_counts)

    for key in ["allOf", "oneOf", "anyOf"]:
        if key in schema and isinstance(schema[key], list):
            for i, sub_schema in enumerate(schema[key]):
                find_non_nullable_fields(sub_schema, f"{path}.{key}[{i}]", type_counts)

    return type_counts

def analyze_spec(spec_path):
    """Analyze a spec file."""
    print(f"\n{'='*60}")
    print(f"Analyzing: {spec_path}")
    print(f"{'='*60}")

    with open(spec_path) as f:
        spec = json.load(f)

    type_counts = defaultdict(int)

    # Analyze component schemas
    if "components" in spec and "schemas" in spec["components"]:
        for schema_name, schema in spec["components"]["schemas"].items():
            find_non_nullable_fields(schema, f"{schema_name}", type_counts)

    # Analyze path operations
    for path, path_item in spec.get("paths", {}).items():
        for method in ["get", "post", "put", "patch", "delete"]:
            if method in path_item:
                operation = path_item[method]

                # Check response schemas
                for code, response in operation.get("responses", {}).items():
                    content = response.get("content", {})
                    for content_type, content_schema in content.items():
                        if "schema" in content_schema:
                            find_non_nullable_fields(
                                content_schema["schema"],
                                f"{path}.{method}.response.{code}",
                                type_counts
                            )

    print(f"\n{'='*60}")
    print("Summary of non-nullable field types:")
    print(f"{'='*60}")
    for field_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {field_type}: {count} occurrences")

    return type_counts

if __name__ == "__main__":
    specs = [
        "fastmcp-fixed-specs/core-v1-openapi.json",
        "fastmcp-fixed-specs/apps-v1-openapi.json",
        "fastmcp-fixed-specs/networking-v1-openapi.json"
    ]

    all_counts = defaultdict(int)

    for spec_path in specs:
        try:
            counts = analyze_spec(spec_path)
            for field_type, count in counts.items():
                all_counts[field_type] += count
        except FileNotFoundError:
            print(f"ERROR: {spec_path} not found")

    print(f"\n{'='*60}")
    print("TOTAL ACROSS ALL SPECS:")
    print(f"{'='*60}")
    for field_type, count in sorted(all_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {field_type}: {count} total occurrences")

    if all_counts:
        print(f"\n⚠️  These field types could cause validation errors if K8s returns null!")
        print("   Consider making ALL types nullable, not just strings.")
