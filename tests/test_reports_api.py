from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import reports
from src.api.app import app


@pytest.fixture(autouse=True)
def _reports_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path)
    return tmp_path


async def test_list_reports_empty_dir_returns_empty_list() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_reports_returns_newest_first(_reports_dir: Path) -> None:
    older = _reports_dir / "20260101T000000Z.json"
    older.write_text(json.dumps({"model": "m", "timestamp": "t1", "splits": {"dev": {}}}))
    newer = _reports_dir / "20260102T000000Z.json"
    newer.write_text(json.dumps({"model": "m", "timestamp": "t2", "splits": {"dev": {}}}))
    import os
    import time

    os.utime(older, (time.time() - 100, time.time() - 100))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports")

    body = response.json()
    assert [r["id"] for r in body] == ["20260102T000000Z", "20260101T000000Z"]


async def test_list_reports_skips_malformed_json(_reports_dir: Path) -> None:
    (_reports_dir / "bad.json").write_text("not json")
    (_reports_dir / "good.json").write_text(json.dumps({"model": "m", "timestamp": "t", "splits": {}}))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports")

    assert [r["id"] for r in response.json()] == ["good"]


async def test_list_reports_filters_by_provider_id(_reports_dir: Path) -> None:
    (_reports_dir / "stripe-a.json").write_text(
        json.dumps({"model": "m", "timestamp": "t", "provider": "stripe", "splits": {}})
    )
    (_reports_dir / "github-b.json").write_text(
        json.dumps({"model": "m", "timestamp": "t", "provider": "github", "splits": {}})
    )
    (_reports_dir / "all-c.json").write_text(
        json.dumps({"model": "m", "timestamp": "t", "providers": ["stripe", "github"], "splits": {}})
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports", params={"provider_id": "github"})

    ids = {r["id"] for r in response.json()}
    assert ids == {"github-b", "all-c"}


async def test_get_report_returns_full_json(_reports_dir: Path) -> None:
    (_reports_dir / "abc.json").write_text(json.dumps({"model": "m", "timestamp": "t", "splits": {"dev": {}}}))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports/abc")

    assert response.status_code == 200
    assert response.json()["model"] == "m"


async def test_get_report_missing_returns_404() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports/does-not-exist")

    assert response.status_code == 404


async def test_get_report_malformed_json_returns_500(_reports_dir: Path) -> None:
    (_reports_dir / "broken.json").write_text("not json")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports/broken")

    assert response.status_code == 500
