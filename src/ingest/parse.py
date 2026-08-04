from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.logging import get_logger

logger = get_logger(__name__)

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_REF_DEPTH = 50
_MAX_COMPOSITION_DEPTH = 50


def _strip_html(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = _HTML_TAG_RE.sub("", text).strip()
    return cleaned or None


@dataclass
class ParsedParameter:
    name: str
    location: str
    type: str | None
    required: bool
    description: str | None


@dataclass
class ParsedEndpoint:
    method: str
    path: str
    operation_id: str
    summary: str | None
    description: str | None
    tags: list[str] = field(default_factory=list)
    parameters: list[ParsedParameter] = field(default_factory=list)


def _resolve_ref(ref: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        logger.warning("ref_unsupported", ref=ref)
        return None
    node: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            logger.warning("ref_missing", ref=ref)
            return None
        node = node[part]
    if not isinstance(node, dict):
        logger.warning("ref_not_object", ref=ref)
        return None
    return node


def _resolve(node: Any, spec: dict[str, Any], seen: frozenset[str], depth: int = 0) -> Any:
    """Recursively dereferences $ref anywhere in the tree - inside allOf/anyOf/oneOf,
    items, additionalProperties, or plain nested objects, since this walks every dict
    value and list element unconditionally. `seen` guards against cycles (a ref that
    directly or indirectly points back at itself); `depth` is a defensive cap against a
    very long but technically non-cyclic ref chain, so a pathological spec degrades to a
    logged warning instead of exhausting Python's recursion limit."""
    if depth > _MAX_REF_DEPTH:
        logger.warning("ref_depth_exceeded", depth=depth)
        return None
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if ref in seen:
                logger.warning("ref_cycle", ref=ref)
                return None
            resolved = _resolve_ref(ref, spec)
            if resolved is None:
                return None
            return _resolve(resolved, spec, seen | {ref}, depth + 1)
        return {key: _resolve(value, spec, seen, depth) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve(item, spec, seen, depth) for item in node]
    return node


def _flatten_schema(schema: Any, depth: int = 0) -> dict[str, Any]:
    """Merges allOf/anyOf/oneOf composition into one flat schema exposing a combined
    properties/required/type, since every caller here only ever reads those three keys
    directly off whatever schema it's handed. allOf is a true merge (every branch always
    applies, per the OpenAPI spec) so unioning properties/required is exact. anyOf/oneOf
    are alternatives, not a merge - unioning their properties anyway is a deliberate
    over-approximation: the goal is "never silently lose a real parameter that some
    branch declares," not spec-perfect validation semantics, which this project has no
    use for. depth is a defensive cap, not an expected limit - real specs nest allOf a
    handful of levels at most."""
    if not isinstance(schema, dict):
        return schema if isinstance(schema, dict) else {}
    if depth > _MAX_COMPOSITION_DEPTH:
        logger.warning("schema_composition_too_deep", depth=depth)
        return schema

    branches: list[Any] | None = None
    for key in ("allOf", "anyOf", "oneOf"):
        value = schema.get(key)
        if isinstance(value, list):
            branches = value
            break
    if branches is None:
        return schema

    merged_properties: dict[str, Any] = {}
    merged_required: set[str] = set(schema.get("required") or [])
    merged_type: Any = schema.get("type")

    for branch in branches:
        flat_branch = _flatten_schema(branch, depth + 1)
        props = flat_branch.get("properties")
        if isinstance(props, dict):
            merged_properties.update(props)
        merged_required |= set(flat_branch.get("required") or [])
        if merged_type is None:
            merged_type = flat_branch.get("type")

    result = dict(schema)
    if merged_properties:
        result["properties"] = merged_properties
    if merged_required:
        result["required"] = sorted(merged_required)
    if merged_type is not None:
        result["type"] = merged_type
    return result


def _param_type(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    flat = _flatten_schema(schema)
    type_ = flat.get("type")
    if isinstance(type_, list):
        # OpenAPI 3.1 allows type as an array, e.g. ["string", "null"] for nullable
        # fields. Report the first non-null type name; "null"-only or empty is unknown.
        non_null = [t for t in type_ if isinstance(t, str) and t != "null"]
        return non_null[0] if non_null else None
    return type_ if isinstance(type_, str) else None


def _parse_parameters(
    raw_params: list[dict[str, Any]], spec: dict[str, Any]
) -> list[ParsedParameter]:
    parsed: list[ParsedParameter] = []
    for raw in raw_params:
        resolved = _resolve(raw, spec, frozenset())
        if not isinstance(resolved, dict):
            continue
        if "name" not in resolved:
            logger.warning("parameter_invalid")
            continue
        parsed.append(
            ParsedParameter(
                name=resolved["name"],
                location=resolved.get("in", "query"),
                type=_param_type(resolved.get("schema")),
                required=bool(resolved.get("required", False)),
                description=_strip_html(resolved.get("description")),
            )
        )
    return parsed


def _request_body_schemas(operation: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Every media-type schema under requestBody.content, not one preferred type - real
    providers differ (Stripe form-encodes almost everything; GitHub and OpenAI use plain
    application/json; some operations declare more than one media type for the same
    body). Returning all of them lets the caller union their parameters rather than
    silently picking one and missing fields only declared under another."""
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return []
    resolved_body = _resolve(request_body, spec, frozenset())
    if not isinstance(resolved_body, dict):
        return []
    content = resolved_body.get("content")
    if not isinstance(content, dict):
        return []
    schemas = []
    for media in content.values():
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            schemas.append(_flatten_schema(media["schema"]))
    return schemas


def _parse_body_parameters(
    operation: dict[str, Any], spec: dict[str, Any]
) -> list[ParsedParameter]:
    parsed: list[ParsedParameter] = []
    seen_names: set[str] = set()
    for schema in _request_body_schemas(operation, spec):
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        required = set(schema.get("required") or [])
        for name, prop_schema in properties.items():
            if name in seen_names or not isinstance(prop_schema, dict):
                continue
            seen_names.add(name)
            parsed.append(
                ParsedParameter(
                    name=name,
                    location="body",
                    type=_param_type(prop_schema),
                    required=name in required,
                    description=_strip_html(prop_schema.get("description")),
                )
            )
    return parsed


def _matches_prefix(path: str, path_prefixes: tuple[str, ...] | None) -> bool:
    if not path_prefixes:
        return True
    return any(path.startswith(prefix) for prefix in path_prefixes)


def _synthesize_operation_id(method: str, path: str) -> str:
    """Some real-world specs omit operationId on some operations (missing entirely, not
    just empty). Synthesizing a stable one from method+path means downstream code -
    find_related, citations, the agent's get_endpoint tool - always has a usable handle
    instead of needing to treat operation_id as optional everywhere it's read."""
    slug = _SLUG_RE.sub("_", path.lower()).strip("_")
    return f"{method.lower()}_{slug}"


def parse_spec(
    spec: dict[str, Any], path_prefixes: tuple[str, ...] | None = None
) -> list[ParsedEndpoint]:
    endpoints: list[ParsedEndpoint] = []
    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            logger.warning("path_item_invalid", path=path)
            continue
        if not _matches_prefix(path, path_prefixes):
            continue
        path_level_params = [p for p in path_item.get("parameters", []) if isinstance(p, dict)]

        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                logger.warning("operation_invalid", path=path, method=method)
                continue

            tags = [t for t in operation.get("tags", []) if isinstance(t, str)]
            op_params = [p for p in operation.get("parameters", []) if isinstance(p, dict)]
            parameters = _parse_parameters(path_level_params + op_params, spec)
            parameters += _parse_body_parameters(operation, spec)

            operation_id = operation.get("operationId") or _synthesize_operation_id(method, path)

            endpoints.append(
                ParsedEndpoint(
                    method=method.upper(),
                    path=path,
                    operation_id=operation_id,
                    summary=_strip_html(operation.get("summary")),
                    description=_strip_html(operation.get("description")),
                    tags=tags,
                    parameters=parameters,
                )
            )

    return endpoints
