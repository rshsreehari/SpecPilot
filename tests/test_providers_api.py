from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import providers as providers_module
from src.api.app import app
from src.api.deps import get_session
from src.models import Provider
from src.providers import ProviderConfig


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
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._rows)


def _provider_row(id_: str, name: str, endpoint_count: int) -> Provider:
    row = Provider(
        id=id_,
        name=name,
        spec_url_or_path="https://example.com/spec.json",
        spec_version=None,
        openapi_version="3.0.0",
        endpoint_count=endpoint_count,
    )
    row.ingested_at = datetime(2026, 1, 1, tzinfo=UTC)
    return row


@pytest.fixture
def override_session() -> Iterator[Any]:
    def _apply(fake: _FakeSession) -> None:
        async def fake_get_session() -> AsyncIterator[_FakeSession]:
            yield fake

        app.dependency_overrides[get_session] = fake_get_session

    yield _apply
    app.dependency_overrides.clear()


async def test_list_providers_marks_configured_but_not_ingested(
    monkeypatch: pytest.MonkeyPatch, override_session: Any
) -> None:
    monkeypatch.setattr(
        providers_module,
        "load_providers",
        lambda: {"stripe": ProviderConfig(id="stripe", name="Stripe", url="x")},
    )
    override_session(_FakeSession(rows=[]))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/providers")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": "stripe",
            "name": "Stripe",
            "ingested": False,
            "endpoint_count": 0,
            "openapi_version": None,
            "ingested_at": None,
            "source": {"type": "url", "location": "x"},
            "origin": "bundled",
            "evaluation_questions_defined": True,
            "evaluation_questions_path": "eval/questions/stripe.yaml",
        }
    ]


async def test_list_providers_reports_ingested_state(
    monkeypatch: pytest.MonkeyPatch, override_session: Any
) -> None:
    monkeypatch.setattr(
        providers_module,
        "load_providers",
        lambda: {"stripe": ProviderConfig(id="stripe", name="Stripe", url="x")},
    )
    override_session(_FakeSession(rows=[_provider_row("stripe", "Stripe", 79)]))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/providers")

    body = response.json()
    assert body[0]["ingested"] is True
    assert body[0]["endpoint_count"] == 79
    assert body[0]["openapi_version"] == "3.0.0"


async def test_list_providers_includes_ingested_rows_missing_from_specs_yaml(
    monkeypatch: pytest.MonkeyPatch, override_session: Any
) -> None:
    monkeypatch.setattr(providers_module, "load_providers", dict)
    override_session(_FakeSession(rows=[_provider_row("orphan", "Orphan", 3)]))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/providers")

    body = response.json()
    assert body == [
        {
            "id": "orphan",
            "name": "Orphan",
            "ingested": True,
            "endpoint_count": 3,
            "openapi_version": "3.0.0",
            "ingested_at": "2026-01-01T00:00:00Z",
            "source": {
                "type": "url",
                "location": "https://example.com/spec.json",
            },
            "origin": "runtime",
            "evaluation_questions_defined": False,
            "evaluation_questions_path": "eval/questions/orphan.yaml",
        }
    ]
