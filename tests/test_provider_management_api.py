from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.api import provider_jobs
from src.api import providers as providers_module
from src.api.app import app
from src.api.deps import get_session
from src.api.provider_jobs import ProviderJobRegistry, run_provider_job
from src.ingest.download import SpecFormatError
from src.ingest.pipeline import DeleteSummary, IngestSummary
from src.models import Provider
from src.providers import ProviderConfig


class _Session:
    def __init__(self, existing: Provider | None = None) -> None:
        self.existing = existing

    async def get(self, _model: Any, _provider_id: str) -> Provider | None:
        return self.existing


class _SessionContext:
    async def __aenter__(self) -> _Session:
        return _Session()

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.fixture
def override_session() -> Iterator[None]:
    async def fake_session() -> AsyncIterator[_Session]:
        yield _Session()

    app.dependency_overrides[get_session] = fake_session
    yield
    app.dependency_overrides.clear()


def _fixture_text() -> str:
    spec = json.loads((Path(__file__).parent / "fixtures" / "small_spec.json").read_text())
    spec["openapi"] = "3.0.0"
    spec["info"] = {"title": "Widget API", "version": "1.0.0"}
    return json.dumps(spec)


async def test_preview_returns_counts_without_database_writes(override_session: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/providers/preview",
            json={"source_type": "upload", "spec_content": _fixture_text()},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["openapi_version"] == "3.0.0"
    assert body["endpoint_count"] == 2
    assert body["sample_paths"] == ["/v1/widgets"]
    assert body["path_prefixes"] == [{"prefix": "/v1", "endpoint_count": 2}]


async def test_preview_detects_yaml_by_content(override_session: None) -> None:
    spec = json.loads(_fixture_text())
    import yaml

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/providers/preview",
            json={"source_type": "upload", "spec_content": yaml.safe_dump(spec)},
        )

    assert response.status_code == 200
    assert response.json()["endpoint_count"] == 2


async def test_preview_rejects_swagger_2_with_readable_version(
    override_session: None,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/providers/preview",
            json={
                "source_type": "upload",
                "spec_content": json.dumps({"swagger": "2.0", "paths": {}}),
            },
        )

    assert response.status_code == 422
    assert "Swagger 2.0" in response.json()["detail"]


@pytest.mark.parametrize("provider_id", ["A", "a", "two_words", "-leading", "trailing-"])
async def test_create_rejects_invalid_provider_ids(
    provider_id: str, override_session: None
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/providers",
            json={
                "source_type": "url",
                "url": "https://example.com/openapi.json",
                "id": provider_id,
                "name": "Example",
            },
        )

    assert response.status_code == 422


async def test_create_returns_409_for_config_collision(
    monkeypatch: pytest.MonkeyPatch, override_session: None
) -> None:
    monkeypatch.setattr(
        providers_module,
        "load_providers",
        lambda: {"taken": ProviderConfig(id="taken", name="Taken", url="x")},
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/providers",
            json={
                "source_type": "url",
                "url": "https://example.com/openapi.json",
                "id": "taken",
                "name": "Taken again",
            },
        )

    assert response.status_code == 409
    assert "already taken" in response.json()["detail"]


async def test_create_url_starts_background_job(
    monkeypatch: pytest.MonkeyPatch, override_session: None
) -> None:
    started: list[str] = []
    monkeypatch.setattr(providers_module, "load_providers", dict)

    def fake_add(
        provider_id: str,
        name: str,
        url: str | None,
        _file_path: str | None,
        path_prefixes: tuple[str, ...],
        origin: str,
    ) -> ProviderConfig:
        assert origin == "runtime"
        return ProviderConfig(
            id=provider_id,
            name=name,
            url=url,
            path_prefixes=path_prefixes,
            origin=origin,
        )

    async def fake_job(job_id: str, provider: ProviderConfig, _path: Path | None) -> None:
        started.append(f"{job_id}:{provider.id}")

    monkeypatch.setattr(providers_module, "add_provider", fake_add)
    monkeypatch.setattr(providers_module, "run_provider_job", fake_job)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/providers",
            json={
                "source_type": "url",
                "url": "https://example.com/openapi.json",
                "id": "acme",
                "name": "Acme",
                "path_prefixes": ["/v1"],
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert response.headers["location"].endswith(body["job_id"])
    assert started == [f"{body['job_id']}:acme"]


async def test_create_upload_uses_managed_file(
    monkeypatch: pytest.MonkeyPatch, override_session: None, tmp_path: Path
) -> None:
    managed_path = tmp_path / "acme.yaml"
    captured: list[str | None] = []
    monkeypatch.setattr(providers_module, "load_providers", dict)

    async def fake_write(_provider_id: str, text: str) -> Path:
        assert "openapi" in text
        return managed_path

    def fake_add(
        provider_id: str,
        name: str,
        _url: str | None,
        file_path: str | None,
        _prefixes: tuple[str, ...],
        _origin: str,
    ) -> ProviderConfig:
        captured.append(file_path)
        return ProviderConfig(id=provider_id, name=name, path=file_path, origin="runtime")

    async def fake_job(*_args: Any) -> None:
        return None

    monkeypatch.setattr(providers_module, "_write_managed_upload", fake_write)
    monkeypatch.setattr(providers_module, "add_provider", fake_add)
    monkeypatch.setattr(providers_module, "run_provider_job", fake_job)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/providers",
            json={
                "source_type": "upload",
                "spec_content": "openapi: 3.0.0\npaths: {}\n",
                "id": "acme",
                "name": "Acme",
            },
        )

    assert response.status_code == 202
    assert captured == [str(managed_path)]


async def test_job_status_known_and_unknown(override_session: None) -> None:
    providers_module.job_registry.clear()
    job = providers_module.job_registry.create("acme")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        known = await client.get(f"/api/providers/jobs/{job.job_id}")
        unknown = await client.get("/api/providers/jobs/missing")

    assert known.status_code == 200
    assert known.json()["status"] == "pending"
    assert unknown.status_code == 404
    assert "stored in memory" in unknown.json()["detail"]


async def test_job_lifecycle_pending_to_done(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ProviderJobRegistry()
    job = registry.create("acme")
    pending = registry.get(job.job_id)
    assert pending is not None
    assert pending.status == "pending"

    async def fake_ingest(
        _session: Any,
        _provider: ProviderConfig,
        refresh: bool,
        progress: Any,
    ) -> IngestSummary:
        assert refresh is True
        await progress("parsing", 0, 0, "Parsing")
        await progress("embedding", 2, 2, "Embedding 2 of 2")
        return IngestSummary("acme", 2, 3, 2)

    monkeypatch.setattr(provider_jobs, "async_session_maker", _SessionContext)
    monkeypatch.setattr(provider_jobs, "run_ingest", fake_ingest)
    await run_provider_job(
        job.job_id,
        ProviderConfig(id="acme", name="Acme", url="x"),
        registry=registry,
    )

    completed = registry.get(job.job_id)
    assert completed is not None
    assert completed.status == "done"
    assert completed.endpoint_count == 2


async def test_job_lifecycle_pending_to_failed_preserves_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ProviderJobRegistry()
    job = registry.create("broken")

    async def fake_ingest(*_args: Any, **_kwargs: Any) -> IngestSummary:
        raise SpecFormatError("the paths object is invalid")

    async def fake_delete(_session: Any, _provider_id: str) -> DeleteSummary:
        return DeleteSummary(0, 0, 0, 0)

    monkeypatch.setattr(provider_jobs, "async_session_maker", _SessionContext)
    monkeypatch.setattr(provider_jobs, "run_ingest", fake_ingest)
    monkeypatch.setattr(provider_jobs, "delete_provider_data", fake_delete)
    await run_provider_job(
        job.job_id,
        ProviderConfig(id="broken", name="Broken", url="x"),
        registry=registry,
        remove_config=lambda _provider_id: True,
    )

    failed = registry.get(job.job_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "the paths object is invalid"


async def test_delete_targets_only_named_provider(
    monkeypatch: pytest.MonkeyPatch, override_session: None
) -> None:
    removed: list[str] = []
    deleted: list[str] = []
    monkeypatch.setattr(
        providers_module,
        "load_providers",
        lambda: {
            "acme": ProviderConfig(id="acme", name="Acme", url="x"),
            "other": ProviderConfig(id="other", name="Other", url="y"),
        },
    )
    monkeypatch.setattr(
        providers_module,
        "remove_provider",
        lambda provider_id: removed.append(provider_id) or True,
    )

    async def fake_delete(_session: Any, provider_id: str) -> DeleteSummary:
        deleted.append(provider_id)
        return DeleteSummary(1, 2, 3, 2)

    async def fake_files(_provider_id: str, _config: ProviderConfig) -> bool:
        return False

    monkeypatch.setattr(providers_module, "delete_provider_data", fake_delete)
    monkeypatch.setattr(providers_module, "_remove_managed_files", fake_files)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/providers/acme")

    assert response.status_code == 200
    assert removed == ["acme"]
    assert deleted == ["acme"]


async def test_delete_refuses_unconfigured_provider(
    monkeypatch: pytest.MonkeyPatch, override_session: None
) -> None:
    monkeypatch.setattr(providers_module, "load_providers", dict)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/providers/missing")

    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]


async def test_remove_managed_upload_and_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    upload = upload_dir / "acme.yaml"
    upload.write_text("openapi: 3.0.0")
    cache = tmp_path / "acme.json"
    cache.write_text("{}")
    monkeypatch.setattr(providers_module, "_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(providers_module, "find_cached_spec_path", lambda _id: cache)

    deleted = await providers_module._remove_managed_files(
        "acme",
        ProviderConfig(id="acme", name="Acme", path=str(upload), origin="runtime"),
    )

    assert deleted is True
    assert not upload.exists()
    assert not cache.exists()
