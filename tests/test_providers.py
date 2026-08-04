from __future__ import annotations

from pathlib import Path

import pytest

from src.providers import (
    ProviderConfigError,
    add_provider,
    get_provider,
    load_providers,
    remove_provider,
    spec_cache_path,
)

_YAML = """
providers:
  - id: stripe
    name: Stripe
    url: https://example.com/stripe.json
    path_prefixes: ["/v1/customers"]
  - id: local-thing
    name: Local Thing
    path: /tmp/local-spec.json
"""


def test_load_providers_parses_url_and_local_entries(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    providers = load_providers(path)

    assert set(providers) == {"stripe", "local-thing"}
    assert providers["stripe"].url == "https://example.com/stripe.json"
    assert providers["stripe"].path_prefixes == ("/v1/customers",)
    assert providers["stripe"].is_local is False
    assert providers["local-thing"].path == "/tmp/local-spec.json"
    assert providers["local-thing"].is_local is True


def test_load_providers_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_providers(tmp_path / "does-not-exist.yaml") == {}


def test_load_providers_rejects_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text("providers:\n  - id: x\n    name: X\n    url: y\n    bogus_key: z\n")

    with pytest.raises(ProviderConfigError, match="unknown key"):
        load_providers(path)


def test_load_providers_rejects_both_url_and_path(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text("providers:\n  - id: x\n    name: X\n    url: y\n    path: z\n")

    with pytest.raises(ProviderConfigError, match="exactly one"):
        load_providers(path)


def test_load_providers_rejects_neither_url_nor_path(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text("providers:\n  - id: x\n    name: X\n")

    with pytest.raises(ProviderConfigError, match="exactly one"):
        load_providers(path)


def test_load_providers_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(
        "providers:\n"
        "  - id: x\n    name: X\n    url: a\n"
        "  - id: x\n    name: X2\n    url: b\n"
    )

    with pytest.raises(ProviderConfigError, match="more than once"):
        load_providers(path)


def test_get_provider_returns_config(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    provider = get_provider("stripe", path)

    assert provider.name == "Stripe"


def test_get_provider_unknown_raises_with_known_providers_listed(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    with pytest.raises(ProviderConfigError, match="stripe"):
        get_provider("nope", path)


def test_add_provider_appends_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    added = add_provider("acme", name="Acme", url="https://example.com/acme.json", path=path)

    assert added.id == "acme"
    reloaded = load_providers(path)
    assert "acme" in reloaded
    assert "stripe" in reloaded  # existing entries preserved


def test_add_provider_defaults_name_to_id(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    added = add_provider("acme", name=None, url="https://example.com/acme.json", path=path)

    assert added.name == "acme"


def test_add_provider_rejects_duplicate_id(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    with pytest.raises(ProviderConfigError, match="already exists"):
        add_provider("stripe", name=None, url="https://example.com/x.json", path=path)


def test_add_provider_creates_file_if_missing(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"

    add_provider("acme", name="Acme", url="https://example.com/acme.json", path=path)

    assert path.is_file()
    assert "acme" in load_providers(path)


def test_remove_provider_removes_entry_and_returns_true(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    removed = remove_provider("stripe", path)

    assert removed is True
    assert "stripe" not in load_providers(path)
    assert "local-thing" in load_providers(path)


def test_remove_provider_returns_false_when_not_present(tmp_path: Path) -> None:
    path = tmp_path / "specs.yaml"
    path.write_text(_YAML)

    assert remove_provider("does-not-exist", path) is False


def test_remove_provider_missing_file_returns_false(tmp_path: Path) -> None:
    assert remove_provider("stripe", tmp_path / "does-not-exist.yaml") is False


def test_spec_cache_path_builds_expected_path() -> None:
    assert spec_cache_path("stripe", "json") == Path("data/specs/stripe.json")
