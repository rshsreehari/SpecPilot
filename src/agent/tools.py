from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Endpoint, Parameter
from src.retrieval.base import Retriever

_PROVIDER_ID_PROPERTY = {
    "provider_id": {
        "type": "string",
        "description": (
            "Optional. Restrict to one ingested provider id. If "
            "omitted, uses whichever provider is currently in scope, or searches every "
            "ingested provider if none is."
        ),
    }
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the API documentation for passages relevant to a query, using "
                "the currently configured retrieval strategy and provider scope."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_endpoint",
            "description": (
                "Get full detail - summary, description, and parameters - for one "
                "specific endpoint identified by HTTP method and path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "description": "HTTP method, e.g. GET, POST"},
                    "path": {
                        "type": "string",
                        "description": "The exact endpoint path, e.g. "
                        "/v1/subscriptions/{subscription_exposed_id}",
                    },
                    **_PROVIDER_ID_PROPERTY,
                },
                "required": ["method", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_parameters",
            "description": (
                "List the parameters - name, location, type, required flag - for one "
                "specific endpoint identified by HTTP method and path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "description": "HTTP method, e.g. GET, POST"},
                    "path": {"type": "string", "description": "The exact endpoint path"},
                    **_PROVIDER_ID_PROPERTY,
                },
                "required": ["method", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_related",
            "description": (
                "Find other endpoints related to a given one (same resource family), "
                "identified by its operation_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation_id": {
                        "type": "string",
                        "description": "The operation_id of the endpoint to find relatives of",
                    },
                    **_PROVIDER_ID_PROPERTY,
                },
                "required": ["operation_id"],
            },
        },
    },
]


class ParameterInfo(BaseModel):
    name: str
    location: str
    type: str | None
    required: bool
    description: str | None


class EndpointRef(BaseModel):
    endpoint_id: int
    provider_id: str
    method: str
    path: str
    operation_id: str | None


@dataclass
class AgentContext:
    session: AsyncSession
    retriever: Retriever
    top_k_default: int = 5
    provider_id: str | None = None


@dataclass
class ToolExecution:
    """result is JSON-serializable, sent back to the model as the tool message content.
    endpoint_ids is every endpoint this call surfaced, used by eval to compute
    wasted_call_rate: calls whose surfaced endpoints never appear in the final answer."""

    result: dict[str, Any]
    endpoint_ids: list[int]


def _parameter_info(param: Parameter) -> ParameterInfo:
    return ParameterInfo(
        name=param.name,
        location=param.location,
        type=param.type,
        required=param.required,
        description=param.description,
    )


async def search_docs(query: str, top_k: int, context: AgentContext) -> ToolExecution:
    chunks = await context.retriever.search(query, top_k)
    return ToolExecution(
        result={
            "results": [
                {
                    "chunk_id": c.chunk_id,
                    "endpoint_id": c.endpoint_id,
                    "provider_id": c.provider_id,
                    "method": c.method,
                    "path": c.path,
                    "operation_id": c.operation_id,
                    "text": c.text,
                    "score": c.score,
                }
                for c in chunks
            ]
        },
        endpoint_ids=[c.endpoint_id for c in chunks],
    )


async def get_endpoint(
    method: str, path: str, context: AgentContext, provider_id: str | None = None
) -> ToolExecution:
    scope = provider_id or context.provider_id
    stmt = select(Endpoint).where(Endpoint.method == method.upper(), Endpoint.path == path)
    if scope is not None:
        stmt = stmt.where(Endpoint.provider_id == scope)
    # .first(), not .scalar_one_or_none(): two providers can share (method, path) once
    # more than one is ingested, and an unscoped lookup must degrade gracefully to "pick
    # one" rather than raise MultipleResultsFound - the model can pass provider_id to
    # disambiguate when it actually matters.
    endpoint = (await context.session.execute(stmt)).scalars().first()
    if endpoint is None:
        return ToolExecution(result={"error": f"no endpoint found for {method} {path}"}, endpoint_ids=[])

    params = (
        (await context.session.execute(select(Parameter).where(Parameter.endpoint_id == endpoint.id)))
        .scalars()
        .all()
    )
    return ToolExecution(
        result={
            "endpoint_id": endpoint.id,
            "provider_id": endpoint.provider_id,
            "method": endpoint.method,
            "path": endpoint.path,
            "operation_id": endpoint.operation_id,
            "summary": endpoint.summary,
            "description": endpoint.description,
            "parameters": [_parameter_info(p).model_dump() for p in params],
        },
        endpoint_ids=[endpoint.id],
    )


async def list_parameters(
    method: str, path: str, context: AgentContext, provider_id: str | None = None
) -> ToolExecution:
    scope = provider_id or context.provider_id
    stmt = select(Endpoint).where(Endpoint.method == method.upper(), Endpoint.path == path)
    if scope is not None:
        stmt = stmt.where(Endpoint.provider_id == scope)
    endpoint = (await context.session.execute(stmt)).scalars().first()
    if endpoint is None:
        return ToolExecution(result={"error": f"no endpoint found for {method} {path}"}, endpoint_ids=[])

    params = (
        (await context.session.execute(select(Parameter).where(Parameter.endpoint_id == endpoint.id)))
        .scalars()
        .all()
    )
    return ToolExecution(
        result={
            "endpoint_id": endpoint.id,
            "provider_id": endpoint.provider_id,
            "method": endpoint.method,
            "path": endpoint.path,
            "parameters": [_parameter_info(p).model_dump() for p in params],
        },
        endpoint_ids=[endpoint.id],
    )


async def find_related(
    operation_id: str, context: AgentContext, provider_id: str | None = None
) -> ToolExecution:
    """"Related" means sharing the same resource path prefix (e.g. every endpoint under
    /v1/subscriptions) within the SAME provider - Stripe's real spec does not populate
    the `tags` field on any operation at all (confirmed in Phase 1 - BUGS.md), so
    tag-based relatedness would always return nothing; path-prefix grouping is the
    practical, working proxy here. Always scoped to one provider (the found endpoint's
    own), since a path-prefix match across unrelated providers would be a coincidence,
    not a real relationship."""
    scope = provider_id or context.provider_id
    stmt = select(Endpoint).where(Endpoint.operation_id == operation_id)
    if scope is not None:
        stmt = stmt.where(Endpoint.provider_id == scope)
    endpoint = (await context.session.execute(stmt)).scalars().first()
    if endpoint is None:
        return ToolExecution(
            result={"error": f"no endpoint found with operation_id {operation_id}"},
            endpoint_ids=[],
        )

    prefix = "/".join(endpoint.path.split("/")[:3])
    related_stmt = select(Endpoint).where(
        Endpoint.path.startswith(prefix),
        Endpoint.provider_id == endpoint.provider_id,
        Endpoint.id != endpoint.id,
    )
    related = (await context.session.execute(related_stmt)).scalars().all()
    refs = [
        EndpointRef(
            endpoint_id=e.id,
            provider_id=e.provider_id,
            method=e.method,
            path=e.path,
            operation_id=e.operation_id,
        )
        for e in related
    ]
    return ToolExecution(
        result={"endpoints": [r.model_dump() for r in refs]},
        endpoint_ids=[r.endpoint_id for r in refs],
    )


async def execute_tool(name: str, args: dict[str, Any], context: AgentContext) -> ToolExecution:
    if name == "search_docs":
        return await search_docs(
            args.get("query", ""), args.get("top_k") or context.top_k_default, context
        )
    if name == "get_endpoint":
        return await get_endpoint(
            args.get("method", ""), args.get("path", ""), context, args.get("provider_id")
        )
    if name == "list_parameters":
        return await list_parameters(
            args.get("method", ""), args.get("path", ""), context, args.get("provider_id")
        )
    if name == "find_related":
        return await find_related(args.get("operation_id", ""), context, args.get("provider_id"))
    return ToolExecution(result={"error": f"unknown tool: {name}"}, endpoint_ids=[])
