from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agent.tools import (
    AgentContext,
    execute_tool,
    find_related,
    get_endpoint,
    list_parameters,
    search_docs,
)
from src.models import Endpoint, Parameter
from src.retrieval.base import RetrievedChunk


@dataclass
class _FakeScalars:
    items: list[Any]

    def all(self) -> list[Any]:
        return self.items

    def first(self) -> Any:
        return self.items[0] if self.items else None


@dataclass
class _FakeResult:
    items: list[Any]

    def scalar_one_or_none(self) -> Any:
        return self.items[0] if self.items else None

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self.items)


class _FakeSession:
    """Scripted responses returned in call order - mocks at the session.execute
    boundary, matching this repo's existing hermetic-test pattern (FakeSession in
    test_query_endpoint.py) rather than hitting a real DB."""

    def __init__(self, responses: list[list[Any]]) -> None:
        self._responses = responses
        self.call_count = 0

    async def execute(self, _stmt: Any) -> _FakeResult:
        items = self._responses[self.call_count]
        self.call_count += 1
        return _FakeResult(items)


class _FakeRetriever:
    async def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=1,
                endpoint_id=42,
                provider_id="stripe",
                text="some text",
                method="GET",
                path="/v1/customers",
                operation_id="GetCustomers",
                score=0.5,
            )
        ]


def _endpoint(
    id_: int = 1,
    method: str = "GET",
    path: str = "/v1/customers/{customer}",
    operation_id: str = "GetCustomersCustomer",
    provider_id: str = "stripe",
) -> Endpoint:
    e = Endpoint(
        method=method,
        path=path,
        operation_id=operation_id,
        summary="s",
        description="d",
        tags=[],
        provider_id=provider_id,
    )
    e.id = id_
    return e


def _parameter(endpoint_id: int = 1, name: str = "customer") -> Parameter:
    p = Parameter(
        endpoint_id=endpoint_id,
        name=name,
        location="path",
        type="string",
        required=True,
        description=None,
        provider_id="stripe",
    )
    p.id = 1
    return p


async def test_search_docs_returns_chunk_metadata_and_endpoint_ids() -> None:
    context = AgentContext(session=_FakeSession([]), retriever=_FakeRetriever())

    execution = await search_docs("customers", 5, context)

    assert execution.endpoint_ids == [42]
    assert execution.result["results"][0]["path"] == "/v1/customers"


async def test_get_endpoint_returns_detail_with_parameters() -> None:
    endpoint = _endpoint()
    session = _FakeSession([[endpoint], [_parameter()]])
    context = AgentContext(session=session, retriever=_FakeRetriever())

    execution = await get_endpoint("GET", "/v1/customers/{customer}", context)

    assert execution.endpoint_ids == [1]
    assert execution.result["operation_id"] == "GetCustomersCustomer"
    assert execution.result["parameters"][0]["name"] == "customer"


async def test_get_endpoint_not_found_returns_error() -> None:
    session = _FakeSession([[]])
    context = AgentContext(session=session, retriever=_FakeRetriever())

    execution = await get_endpoint("GET", "/v1/nonexistent", context)

    assert execution.endpoint_ids == []
    assert "error" in execution.result


async def test_list_parameters_returns_parameters_only() -> None:
    endpoint = _endpoint()
    session = _FakeSession([[endpoint], [_parameter()]])
    context = AgentContext(session=session, retriever=_FakeRetriever())

    execution = await list_parameters("GET", "/v1/customers/{customer}", context)

    assert "summary" not in execution.result
    assert execution.result["parameters"][0]["name"] == "customer"


async def test_list_parameters_not_found_returns_error() -> None:
    session = _FakeSession([[]])
    context = AgentContext(session=session, retriever=_FakeRetriever())

    execution = await list_parameters("GET", "/v1/nonexistent", context)

    assert execution.result == {"error": "no endpoint found for GET /v1/nonexistent"}


async def test_find_related_groups_by_path_prefix() -> None:
    origin = _endpoint(id_=1, path="/v1/subscriptions/{id}/resume", operation_id="Resume")
    related = _endpoint(id_=2, path="/v1/subscriptions", operation_id="ListSubscriptions")
    session = _FakeSession([[origin], [related]])
    context = AgentContext(session=session, retriever=_FakeRetriever())

    execution = await find_related("Resume", context)

    assert execution.endpoint_ids == [2]
    assert execution.result["endpoints"][0]["path"] == "/v1/subscriptions"


async def test_find_related_not_found_returns_error() -> None:
    session = _FakeSession([[]])
    context = AgentContext(session=session, retriever=_FakeRetriever())

    execution = await find_related("DoesNotExist", context)

    assert execution.endpoint_ids == []
    assert "error" in execution.result


async def test_execute_tool_dispatches_by_name() -> None:
    context = AgentContext(session=_FakeSession([]), retriever=_FakeRetriever())

    execution = await execute_tool("search_docs", {"query": "x"}, context)

    assert execution.endpoint_ids == [42]


async def test_execute_tool_unknown_name_returns_error() -> None:
    context = AgentContext(session=_FakeSession([]), retriever=_FakeRetriever())

    execution = await execute_tool("not_a_real_tool", {}, context)

    assert execution.result == {"error": "unknown tool: not_a_real_tool"}
