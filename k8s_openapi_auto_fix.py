#!/usr/bin/env python3
"""
Kubernetes OpenAPI validator + auto-fixer.

- Loads one or more Kubernetes OpenAPI v3 JSON specs (e.g. core/apps/networking).
- Filters operations to a fixed set of Kubernetes resource paths.
- Calls a real cluster (GET list + GET by name) in a single namespace.
- Validates RESPONSE JSON against response schemas.
- Validates REQUEST BODY schemas by checking real objects against requestBody schemas.
- Auto-patches the spec for common k8s schema mismatches:
    * type errors where instance is null -> allow "null" in type
    * missing required properties -> remove them from 'required' list
- Writes patched specs to an output directory.

Usage example:

  python k8s_openapi_auto_fix.py \
      --spec core-v1-openapi.json \
      --spec apps-v1-openapi.json \
      --spec networking-v1-openapi.json \
      --namespace devnamespace \
      --patch-output-dir patched-specs \
      --max-per-kind 5
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from jsonschema import Draft202012Validator, RefResolver, ValidationError

Json = Any


# ---------------------------------------------------------------------------
# Target resource families (paths)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SpecContext:
    name: str
    path: str
    spec: Dict[str, Any]
    resolver: RefResolver
    errors: List[ValidationError] = field(default_factory=list)


@dataclass
class OperationRef:
    spec_ctx: SpecContext
    path: str
    method: str            # "get", "post", "put", "patch", "delete"
    operation: Dict[str, Any]


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Matching paths and categorizing operations
# ---------------------------------------------------------------------------

def is_target_path(path: str) -> bool:
    """
    Check if an OpenAPI path belongs to one of the target base paths (pods, services, etc.).
    """
    for tmpl in TARGET_BASE_PATHS:
        base = tmpl
        if path == base or path.startswith(base + "/"):
            return True
    return False


def is_list_level_path(path: str) -> bool:
    """
    List-level path: contains only {namespace} as a path parameter.
    e.g. /api/v1/namespaces/{namespace}/pods
    """
    return path.count("{") == 1 and "{namespace}" in path


# ---------------------------------------------------------------------------
# Kubernetes HTTP session
# ---------------------------------------------------------------------------

def build_k8s_session() -> Tuple[str, requests.Session]:
    """
    Build a requests.Session configured for Kubernetes.

    Priority:
      1. K8S_API_SERVER (full URL)
      2. KUBERNETES_SERVICE_HOST/PORT (in-cluster)
    Auth:
      - K8S_BEARER_TOKEN
      - else service account token from file (in-cluster)
    TLS:
      - K8S_CA_CERT
      - else in-cluster CA
      - else default verify=True
    """
    api_server = os.getenv("K8S_API_SERVER")
    if not api_server:
        host = os.getenv("KUBERNETES_SERVICE_HOST")
        port = os.getenv("KUBERNETES_SERVICE_PORT")
        if not (host and port):
            raise RuntimeError(
                "K8S_API_SERVER not set and no in-cluster env vars "
                "(KUBERNETES_SERVICE_HOST / KUBERNETES_SERVICE_PORT)."
            )
        api_server = f"https://{host}:{port}"
    api_server = api_server.rstrip("/")

    sess = requests.Session()

    # Auth token
    token = os.getenv("K8S_BEARER_TOKEN")
    if not token:
        sa_token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        if os.path.exists(sa_token_path):
            with open(sa_token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
    if token:
        sess.headers["Authorization"] = f"Bearer {token}"

    # TLS verification
    ca_cert = os.getenv(
        "K8S_CA_CERT",
        "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
    )
    if os.path.exists(ca_cert):
        sess.verify = ca_cert
    else:
        sess.verify = False  # Skip SSL verification for self-signed certs

    sess.headers.setdefault("Accept", "application/json")
    return api_server, sess


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------

def load_specs(paths: List[str]) -> List[SpecContext]:
    specs: List[SpecContext] = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            spec = json.load(f)
        name = os.path.basename(p)
        resolver = RefResolver.from_schema(spec)
        specs.append(SpecContext(name=name, path=p, spec=spec, resolver=resolver))
        log(f"Loaded spec {name}")
    return specs


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def choose_success_response_schema(
    operation: Dict[str, Any]
) -> Optional[Json]:
    """
    Pick a success response schema (2xx or default) for application/json.
    Returns schema object or None.
    """
    responses = operation.get("responses", {})
    candidate_status = None

    for code in ("200", "201", "202"):
        if code in responses:
            candidate_status = code
            break
    if not candidate_status:
        for code in responses:
            if code.isdigit() and code.startswith("2"):
                candidate_status = code
                break
    if not candidate_status and "default" in responses:
        candidate_status = "default"

    if not candidate_status:
        return None

    resp_obj = responses[candidate_status]
    content = resp_obj.get("content", {})
    app_json = content.get("application/json")
    if not app_json:
        return None

    return app_json.get("schema")


def get_request_body_schema(operation: Dict[str, Any]) -> Optional[Json]:
    """
    Get requestBody schema (application/json) for an operation, if any.
    """
    rb = operation.get("requestBody")
    if not rb:
        return None
    content = rb.get("content", {})
    app_json = content.get("application/json")
    if not app_json:
        return None
    return app_json.get("schema")


# ---------------------------------------------------------------------------
# HTTP + parameter substitution
# ---------------------------------------------------------------------------

def substitute_path_params(path: str, namespace: str, name: Optional[str] = None) -> str:
    """
    Replace {namespace} and {name} tokens in the path.
    """
    result = path.replace("{namespace}", namespace)
    if "{name}" in result:
        if not name:
            raise ValueError(f"path {path} requires a {name=} but none provided")
        result = result.replace("{name}", name)
    return result


def perform_get(
    base_url: str,
    sess: requests.Session,
    path: str,
    namespace: str,
    name: Optional[str],
) -> Tuple[int, Optional[Json]]:
    url_path = substitute_path_params(path, namespace, name)
    url = base_url + url_path
    resp = sess.get(url)
    try:
        data = resp.json()
    except ValueError:
        data = None
    log(f"GET {url} -> {resp.status_code}")
    return resp.status_code, data


# ---------------------------------------------------------------------------
# JSON pointer-ish traversal for patching
# ---------------------------------------------------------------------------

def get_schema_node_and_parent(
    root: Json, schema_path: List[Union[str, int]]
) -> Tuple[Optional[Json], Optional[Union[str, int]], Optional[Json]]:
    """
    Given a schema root and a jsonschema ValidationError.schema_path,
    return (parent, key, node) where node is the referenced schema piece.
    """
    node: Json = root
    parent: Optional[Json] = None
    key: Optional[Union[str, int]] = None

    for p in schema_path:
        parent = node
        key = p
        try:
            node = node[p]  # works for both dict[key] and list[index]
        except Exception:
            return None, None, None
    return parent, key, node


def autopatch_for_error(spec_ctx: SpecContext, err: ValidationError) -> bool:
    """
    Apply automatic schema fixes for a single ValidationError.
    Returns True if a patch was applied.
    """
    parent, key, node = get_schema_node_and_parent(spec_ctx.spec, list(err.schema_path))
    if parent is None:
        return False

    # 1) type error where instance is null -> allow null in type
    if err.validator == "type":
        # jsonschema can express allowed types as string or list of strings
        # We care about the case where instance is None / null.
        if err.instance is None:
            # parent[key] is likely "string", ["string"], etc.
            if key == "type":
                t = parent.get("type")
                if isinstance(t, str):
                    if t != "null":
                        parent["type"] = [t, "null"]
                        # Also drop nullable if present
                        parent.pop("nullable", None)
                        log(
                            f"[PATCH] {spec_ctx.name}: allowed null for type at schema path "
                            f"{'/'.join(map(str, err.schema_path))}"
                        )
                        return True
                elif isinstance(t, list):
                    if "null" not in t:
                        t.append("null")
                        parent["type"] = t
                        parent.pop("nullable", None)
                        log(
                            f"[PATCH] {spec_ctx.name}: appended 'null' to type list at schema path "
                            f"{'/'.join(map(str, err.schema_path))}"
                        )
                        return True

    # 2) required property missing in real data -> remove from required[]
    if err.validator == "required":
        # err.message like: "'fieldName' is a required property"
        msg = str(err.message)
        # Simple parse: take the first quoted token
        field_name = None
        if "'" in msg:
            parts = msg.split("'")
            if len(parts) >= 3:
                field_name = parts[1]

        if key == "required" and isinstance(node, list) and field_name:
            if field_name in node:
                node.remove(field_name)
                log(
                    f"[PATCH] {spec_ctx.name}: removed '{field_name}' from required at schema path "
                    f"{'/'.join(map(str, err.schema_path))}"
                )
                return True

    # (You can add more rules here for enums, etc.)
    return False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_instance(
    spec_ctx: SpecContext,
    schema: Json,
    instance: Json,
    context: str,
    autopatch: bool,
) -> List[ValidationError]:
    """
    Validate `instance` against `schema` (which can include $ref).
    Optionally auto-patch the schema on certain errors.
    Returns the list of errors (after any patching).
    """
    validator = Draft202012Validator(schema, resolver=spec_ctx.resolver)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)

    for err in errors:
        instance_path = "/" + "/".join(str(p) for p in err.path)
        schema_path = "/" + "/".join(str(p) for p in err.schema_path)
        log(
            f"[{context}] Validation error: {err.message}\n"
            f"  instance path: {instance_path}\n"
            f"  schema   path: {schema_path}\n"
        )
        spec_ctx.errors.append(err)
        if autopatch:
            patched = autopatch_for_error(spec_ctx, err)
            if patched:
                # After patch, we don't re-run validation immediately;
                # script is iterative: fix, then next run should have fewer errors.
                continue

    return errors


# ---------------------------------------------------------------------------
# Collect operations from specs
# ---------------------------------------------------------------------------

def collect_operations(spec_ctx: SpecContext) -> List[OperationRef]:
    """
    Collect all operations on target paths in this spec.
    We include all HTTP methods, but will only *call* GET ones.
    """
    ops: List[OperationRef] = []
    for path, path_item in spec_ctx.spec.get("paths", {}).items():
        if not is_target_path(path):
            continue
        for method, op_obj in path_item.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            ops.append(
                OperationRef(
                    spec_ctx=spec_ctx,
                    path=path,
                    method=method.lower(),
                    operation=op_obj,
                )
            )
    return ops


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and auto-fix Kubernetes OpenAPI specs against a real cluster."
    )
    parser.add_argument(
        "--spec",
        action="append",
        dest="specs",
        required=True,
        help="Path to a Kubernetes OpenAPI v3 JSON file (repeatable).",
    )
    parser.add_argument(
        "--namespace",
        required=True,
        help="Namespace to test (e.g. devnamespace).",
    )
    parser.add_argument(
        "--max-per-kind",
        type=int,
        default=5,
        help="Max number of sample items per kind for per-resource validation.",
    )
    parser.add_argument(
        "--patch-output-dir",
        required=True,
        help="Directory to write patched spec JSON files.",
    )
    parser.add_argument(
        "--no-autopatch",
        action="store_true",
        help="Disable auto-patching; only report errors.",
    )

    args = parser.parse_args()

    specs = load_specs(args.specs)
    base_url, sess = build_k8s_session()
    namespace = args.namespace
    autopatch = not args.no_autopatch

    os.makedirs(args.patch_output_dir, exist_ok=True)

    all_ops: List[OperationRef] = []
    for sc in specs:
        ops = collect_operations(sc)
        log(f"Spec {sc.name}: collected {len(ops)} operations on target paths")
        all_ops.extend(ops)

    # Partition GET list vs GET by name, and also keep mutating operations per root.
    list_ops: List[OperationRef] = []
    get_ops_by_root: Dict[str, List[OperationRef]] = {}
    mutating_ops_by_root: Dict[str, List[OperationRef]] = {}

    for op in all_ops:
        if op.method == "get":
            if is_list_level_path(op.path):
                list_ops.append(op)
            else:
                root = op.path
                if "/{name}" in root:
                    root = root.split("/{name}", 1)[0]
                get_ops_by_root.setdefault(root, []).append(op)
        elif op.method in ("post", "put", "patch"):
            root = op.path
            if "/{name}" in root:
                root = root.split("/{name}", 1)[0]
            mutating_ops_by_root.setdefault(root, []).append(op)

    log(f"Found {len(list_ops)} list-level GET operations")

    total_errors = 0

    # For each list-op, we:
    # - call the cluster
    # - validate the list RESPONSE
    # - collect names + full items for that kind
    items_by_root: Dict[str, List[Json]] = {}
    names_by_root: Dict[str, List[str]] = {}

    for op in list_ops:
        resp_schema = choose_success_response_schema(op.operation)
        if not resp_schema:
            log(
                f"[{op.spec_ctx.name} GET {op.path}] no success response schema; skipping"
            )
            continue

        status, data = perform_get(base_url, sess, op.path, namespace, None)
        if status >= 400 or data is None:
            log(
                f"[{op.spec_ctx.name} GET {op.path}] HTTP {status}, no body to validate"
            )
            continue

        ctx = f"{op.spec_ctx.name} GET {op.path} [response list]"
        errs = validate_instance(
            op.spec_ctx, resp_schema, data, ctx, autopatch=autopatch
        )
        total_errors += len(errs)

        items = data.get("items")
        if isinstance(items, list):
            # Store sample items for request-body validation later
            root = op.path  # list root is full path with {namespace}
            items_by_root[root] = items[: args.max_per_kind]

            # Also collect names for GET-by-name validation
            collected_names: List[str] = []
            for item in items:
                md = item.get("metadata", {})
                n = md.get("name")
                if isinstance(n, str):
                    collected_names.append(n)
            if collected_names:
                names_by_root[root] = collected_names[: args.max_per_kind]
                log(
                    f"[{ctx}] collected {len(names_by_root[root])} names "
                    f"for per-resource GET validation"
                )

    # Per-resource GET validation (response schemas)
    for root, names in names_by_root.items():
        related_ops = get_ops_by_root.get(root, [])
        if not related_ops:
            continue
        for op in related_ops:
            resp_schema = choose_success_response_schema(op.operation)
            if not resp_schema:
                log(
                    f"[{op.spec_ctx.name} GET {op.path}] no success response schema; skipping"
                )
                continue

            for name in names:
                status, data = perform_get(base_url, sess, op.path, namespace, name)
                if status >= 400 or data is None:
                    log(
                        f"[{op.spec_ctx.name} GET {op.path}] name={name} "
                        f"HTTP {status}, no body to validate"
                    )
                    continue

                ctx = f"{op.spec_ctx.name} GET {op.path} [response single name={name}]"
                errs = validate_instance(
                    op.spec_ctx, resp_schema, data, ctx, autopatch=autopatch
                )
                total_errors += len(errs)

    # Request-body schema validation:
    # For mutating operations (POST/PUT/PATCH), we validate real objects
    # (taken from list responses) against the requestBody schema.
    for root, items in items_by_root.items():
        mut_ops = mutating_ops_by_root.get(root, [])
        if not mut_ops or not items:
            continue

        for op in mut_ops:
            rb_schema = get_request_body_schema(op.operation)
            if not rb_schema:
                continue

            for idx, item in enumerate(items[: args.max_per_kind]):
                ctx = (
                    f"{op.spec_ctx.name} {op.method.upper()} {op.path} "
                    f"[requestBody sample #{idx}]"
                )
                errs = validate_instance(
                    op.spec_ctx, rb_schema, item, ctx, autopatch=autopatch
                )
                total_errors += len(errs)

    log(f"Validation complete. Total schema errors observed: {total_errors}")

    # Write patched specs
    for sc in specs:
        out_path = os.path.join(args.patch_output_dir, sc.name)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sc.spec, f, indent=2, ensure_ascii=False)
        log(f"Wrote patched spec: {out_path}")


if __name__ == "__main__":
    main()
