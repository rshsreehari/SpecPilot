from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SPECS_PATH = Path("specs.yaml")
SPEC_CACHE_DIR = Path("data/specs")

_ALLOWED_KEYS = {"id", "name", "url", "path", "path_prefixes", "origin"}


class ProviderConfigError(ValueError):
    """Raised when specs.yaml is malformed - always names the offending provider."""


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    name: str
    url: str | None = None
    path: str | None = None
    path_prefixes: tuple[str, ...] = field(default_factory=tuple)
    origin: str = "bundled"

    @property
    def is_local(self) -> bool:
        return self.path is not None


def _validate_entry(entry: dict[str, Any]) -> None:
    provider_id = entry.get("id", "<unknown>")
    unknown_keys = set(entry) - _ALLOWED_KEYS
    if unknown_keys:
        raise ProviderConfigError(
            f"provider {provider_id!r}: unknown key(s) {sorted(unknown_keys)} in specs.yaml"
        )
    if "id" not in entry or not entry["id"]:
        raise ProviderConfigError("a provider entry in specs.yaml is missing 'id'")
    if "name" not in entry or not entry["name"]:
        raise ProviderConfigError(f"provider {provider_id!r}: missing 'name'")
    has_url = bool(entry.get("url"))
    has_path = bool(entry.get("path"))
    if has_url == has_path:
        raise ProviderConfigError(
            f"provider {provider_id!r}: specify exactly one of 'url' or 'path', not both/neither"
        )
    if entry.get("origin", "bundled") not in {"bundled", "runtime"}:
        raise ProviderConfigError(
            f"provider {provider_id!r}: origin must be 'bundled' or 'runtime'"
        )


def _parse_entry(entry: dict[str, Any]) -> ProviderConfig:
    _validate_entry(entry)
    prefixes = entry.get("path_prefixes") or []
    if not isinstance(prefixes, list) or not all(isinstance(p, str) for p in prefixes):
        raise ProviderConfigError(f"provider {entry['id']!r}: path_prefixes must be a list of strings")
    return ProviderConfig(
        id=entry["id"],
        name=entry["name"],
        url=entry.get("url"),
        path=entry.get("path"),
        path_prefixes=tuple(prefixes),
        origin=entry.get("origin", "bundled"),
    )


def load_providers(path: Path = SPECS_PATH) -> dict[str, ProviderConfig]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    entries = raw.get("providers", [])
    providers: dict[str, ProviderConfig] = {}
    for entry in entries:
        config = _parse_entry(entry)
        if config.id in providers:
            raise ProviderConfigError(f"provider {config.id!r} is defined more than once in specs.yaml")
        providers[config.id] = config
    return providers


def get_provider(provider_id: str, path: Path = SPECS_PATH) -> ProviderConfig:
    providers = load_providers(path)
    if provider_id not in providers:
        raise ProviderConfigError(
            f"provider {provider_id!r} is not configured in specs.yaml. "
            f"Known providers: {sorted(providers) or 'none'}"
        )
    return providers[provider_id]


def add_provider(
    provider_id: str,
    name: str | None = None,
    url: str | None = None,
    file_path: str | None = None,
    path_prefixes: tuple[str, ...] = (),
    origin: str = "runtime",
    path: Path = SPECS_PATH,
) -> ProviderConfig:
    """Appends an ad hoc provider (specpilot ingest --url/--file --id) to specs.yaml so
    it's a permanent, re-ingestible entry afterward, not a one-off in-memory config."""
    raw: dict[str, Any] = {}
    if path.is_file():
        raw = yaml.safe_load(path.read_text()) or {}
    entries: list[dict[str, Any]] = raw.setdefault("providers", [])

    if any(e.get("id") == provider_id for e in entries):
        raise ProviderConfigError(f"provider {provider_id!r} already exists in specs.yaml")

    entry: dict[str, Any] = {"id": provider_id, "name": name or provider_id}
    if url:
        entry["url"] = url
    if file_path:
        entry["path"] = file_path
    entry["path_prefixes"] = list(path_prefixes)
    entry["origin"] = origin
    entries.append(entry)

    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return _parse_entry(entry)


def remove_provider(provider_id: str, path: Path = SPECS_PATH) -> bool:
    """Removes a provider from specs.yaml. Returns False if it wasn't present. Does not
    touch the database - callers are responsible for deleting the provider's rows."""
    if not path.is_file():
        return False
    raw = yaml.safe_load(path.read_text()) or {}
    entries: list[dict[str, Any]] = raw.get("providers", [])
    remaining = [e for e in entries if e.get("id") != provider_id]
    if len(remaining) == len(entries):
        return False
    raw["providers"] = remaining
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return True


def spec_cache_path(provider_id: str, ext: str) -> Path:
    return SPEC_CACHE_DIR / f"{provider_id}.{ext}"


def find_cached_spec_path(provider_id: str) -> Path | None:
    for ext in ("json", "yaml"):
        candidate = spec_cache_path(provider_id, ext)
        if candidate.is_file():
            return candidate
    return None
