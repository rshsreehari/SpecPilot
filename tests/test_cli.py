from __future__ import annotations

import sys
from typing import Any, Self

import pytest

from src import cli
from src.ingest.pipeline import IngestSummary
from src.providers import ProviderConfig


class _FakeSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _set_argv(monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["specpilot", *args])


def test_ingest_provider_dispatches_to_run_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    async def fake_run_ingest(session: Any, provider: ProviderConfig, refresh: bool) -> IngestSummary:
        calls.append((provider.id, refresh))
        return IngestSummary(provider.id, endpoints_parsed=5, parameters_extracted=10, chunks_embedded=5)

    monkeypatch.setattr(cli, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(cli, "async_session_maker", lambda: _FakeSession())
    monkeypatch.setattr(cli, "get_provider", lambda pid: ProviderConfig(id=pid, name="Stripe", url="x"))
    _set_argv(monkeypatch, "ingest", "--provider", "stripe")

    cli.main()

    assert calls == [("stripe", False)]


def test_ingest_all_dispatches_once_per_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_run_ingest(session: Any, provider: ProviderConfig, refresh: bool) -> IngestSummary:
        calls.append(provider.id)
        return IngestSummary(provider.id, endpoints_parsed=1, parameters_extracted=1, chunks_embedded=1)

    monkeypatch.setattr(cli, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(cli, "async_session_maker", lambda: _FakeSession())
    monkeypatch.setattr(
        cli,
        "load_providers",
        lambda: {
            "stripe": ProviderConfig(id="stripe", name="Stripe", url="x"),
            "github": ProviderConfig(id="github", name="GitHub", url="y"),
        },
    )
    _set_argv(monkeypatch, "ingest", "--all")

    cli.main()

    assert sorted(calls) == ["github", "stripe"]


def test_ingest_url_appends_provider_and_ingests_it(monkeypatch: pytest.MonkeyPatch) -> None:
    added: dict[str, Any] = {}
    ingested: list[str] = []

    def fake_add_provider(provider_id: str, name: Any, url: Any, file_path: Any) -> ProviderConfig:
        added.update(id=provider_id, name=name, url=url, file_path=file_path)
        return ProviderConfig(id=provider_id, name=name or provider_id, url=url)

    async def fake_run_ingest(session: Any, provider: ProviderConfig, refresh: bool) -> IngestSummary:
        ingested.append(provider.id)
        return IngestSummary(provider.id, endpoints_parsed=1, parameters_extracted=1, chunks_embedded=1)

    monkeypatch.setattr(cli, "add_provider", fake_add_provider)
    monkeypatch.setattr(cli, "run_ingest", fake_run_ingest)
    monkeypatch.setattr(cli, "async_session_maker", lambda: _FakeSession())
    _set_argv(monkeypatch, "ingest", "--url", "https://example.com/spec.json", "--id", "acme", "--name", "Acme")

    cli.main()

    assert added == {
        "id": "acme",
        "name": "Acme",
        "url": "https://example.com/spec.json",
        "file_path": None,
    }
    assert ingested == ["acme"]


def test_ingest_url_without_id_fails_clearly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _set_argv(monkeypatch, "ingest", "--url", "https://example.com/spec.json")

    cli.main()

    assert "FAIL --id is required" in capsys.readouterr().out


def test_providers_list_reports_configured_and_ingested_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli, "load_providers", lambda: {"stripe": ProviderConfig(id="stripe", name="Stripe", url="x")}
    )
    monkeypatch.setattr(cli, "_ingested_providers", _make_async(dict))
    _set_argv(monkeypatch, "providers", "list")

    cli.main()

    assert "stripe" in capsys.readouterr().out


def test_providers_remove_dispatches_to_delete_provider_data(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli, "remove_provider", lambda pid: calls.append(f"config:{pid}") or True)

    async def fake_delete(session: Any, provider_id: str) -> None:
        calls.append(f"data:{provider_id}")

    monkeypatch.setattr(cli, "delete_provider_data", fake_delete)
    monkeypatch.setattr(cli, "async_session_maker", lambda: _FakeSession())
    _set_argv(monkeypatch, "providers", "remove", "stripe")

    cli.main()

    assert calls == ["config:stripe", "data:stripe"]


def test_eval_single_pass_dispatches_to_run_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_eval(
        provider_id: str, split: str, seed: int | None, strategy: str | None
    ) -> dict[str, Any]:
        captured.update(provider_id=provider_id, split=split, seed=seed, strategy=strategy)
        return {"splits": {"dev": {}}}

    monkeypatch.setattr(cli, "run_eval", fake_run_eval)
    _set_argv(
        monkeypatch, "eval", "--provider", "stripe", "--split", "dev", "--seed", "7", "--strategy", "bm25"
    )

    cli.main()

    assert captured == {"provider_id": "stripe", "split": "dev", "seed": 7, "strategy": "bm25"}


def test_eval_agent_mode_dispatches_to_run_agent_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_agent_eval(provider_id: str, split: str, seed: int | None) -> dict[str, Any]:
        captured.update(provider_id=provider_id, split=split, seed=seed)
        return {"splits": {"dev": {}}}

    monkeypatch.setattr(cli, "run_agent_eval", fake_run_agent_eval)
    _set_argv(monkeypatch, "eval", "--provider", "stripe", "--mode", "agent", "--split", "dev")

    cli.main()

    assert captured == {"provider_id": "stripe", "split": "dev", "seed": None}


def test_eval_all_providers_dispatches_to_run_eval_all_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_eval_all(split: str, seed: int | None, strategy: str | None) -> dict[str, Any]:
        captured.update(split=split, seed=seed, strategy=strategy)
        return {"splits": {"dev": {}}}

    monkeypatch.setattr(cli, "run_eval_all_providers", fake_run_eval_all)
    _set_argv(monkeypatch, "eval", "--all-providers", "--split", "dev")

    cli.main()

    assert captured == {"split": "dev", "seed": None, "strategy": None}


def test_compare_dispatches_to_run_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_compare(provider_id: str, split: str, seed: int | None) -> dict[str, Any]:
        captured.update(provider_id=provider_id, split=split, seed=seed)
        return {"splits": {"dev": {}}}

    monkeypatch.setattr(cli, "run_compare", fake_run_compare)
    _set_argv(monkeypatch, "compare", "--provider", "stripe", "--split", "holdout")

    cli.main()

    assert captured == {"provider_id": "stripe", "split": "holdout", "seed": None}


def test_compare_all_providers_dispatches_to_run_compare_all_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_compare_all(split: str, seed: int | None) -> dict[str, Any]:
        captured.update(split=split, seed=seed)
        return {"splits": {"dev": {}}}

    monkeypatch.setattr(cli, "run_compare_all_providers", fake_run_compare_all)
    _set_argv(monkeypatch, "compare", "--all-providers")

    cli.main()

    assert captured == {"split": "all", "seed": None}


def test_eval_requires_a_provider_or_all_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_argv(monkeypatch, "eval", "--strategy", "not-a-real-strategy")

    with pytest.raises(SystemExit):
        cli.main()


def _make_async(fn: Any) -> Any:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return wrapper
