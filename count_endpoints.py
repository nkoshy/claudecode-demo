#!/usr/bin/env python3
import json

with open("fastmcp-fixed-specs/apps-v1-openapi.json") as f:
    spec = json.load(f)

paths = spec.get("paths", {})
total_paths = len(paths)
total_endpoints = 0

for path, operations in paths.items():
    # Count actual HTTP methods (exclude 'parameters' which is not a method)
    methods = [m for m in operations.keys() if m != "parameters"]
    total_endpoints += len(methods)

print(f"apps-v1-openapi.json:")
print(f"  Paths: {total_paths}")
print(f"  API Endpoints (HTTP methods): {total_endpoints}")
print(f"\nBreakdown by resource:")

resources = {}
for path, operations in paths.items():
    # Extract resource type (daemonsets, deployments, etc)
    if "daemonsets" in path:
        resource = "DaemonSets"
    elif "deployments" in path:
        resource = "Deployments"
    elif "replicasets" in path:
        resource = "ReplicaSets"
    elif "statefulsets" in path:
        resource = "StatefulSets"
    else:
        resource = "Other"

    methods = [m for m in operations.keys() if m != "parameters"]
    resources[resource] = resources.get(resource, 0) + len(methods)

for resource, count in sorted(resources.items()):
    print(f"  {resource}: {count} endpoints")
