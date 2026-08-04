from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.app import app
from src.api.deps import get_session
from src.models import Endpoint, Parameter


@dataclass
class _FakeScalars:
    items: list[Any]

    def all(self) -> list[Any]:
        return self.items


@dataclass
class _FakeResult:
    items: list[Any]

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self.items)


class _FakeSession:
    def __init__(self, rows: list[Any], get_result: Any = None) -> None:
        self._rows = rows
        self._get_result = get_result

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._rows)

    async def get(self, _model: Any, _id: Any) -> Any:
        return self._get_result


def _endpoint(id_: int = 1) -> Endpoint:
    e = Endpoint(
        provider_id="stripe",
        method="GET",
        path="/v1/customers",
        operation_id="GetCustomers",
        summary="List",
        description="d",
        tags=[],
    )
    e.id = id_
    return e


def _parameter() -> Parameter:
    p = Parameter(
        provider_id="stripe",
        endpoint_id=1,
        name="limit",
        location="query",
        type="integer",
        required=False,
        description=None,
    )
    p.id = 1
    return p


@pytest.fixture
def override_session() -> Iterator[type]:
    def _apply(fake: _FakeSession) -> None:
        async def fake_get_session() -> AsyncIterator[_FakeSession]:
            yield fake

        app.dependency_overrides[get_session] = fake_get_session

    yield _apply
    app.dependency_overrides.clear()


async def test_list_endpoints_returns_summaries(override_session: Any) -> None:
    override_session(_FakeSession(rows=[_endpoint()]))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/endpoints")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["path"] == "/v1/customers"
    assert body[0]["operation_id"] == "GetCustomers"
    assert body[0]["provider_id"] == "stripe"


async def test_get_endpoint_detail_includes_parameters(override_session: Any) -> None:
    override_session(_FakeSession(rows=[_parameter()], get_result=_endpoint()))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/endpoints/1")

    assert response.status_code == 200
    body = response.json()
    assert body["parameters"][0]["name"] == "limit"


async def test_get_endpoint_detail_missing_returns_404(override_session: Any) -> None:
    override_session(_FakeSession(rows=[], get_result=None))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/endpoints/999")

    assert response.status_code == 404
