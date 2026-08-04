from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

from src.ingest.download import parse_spec_text
from src.ingest.parse import parse_spec
from src.providers import ProviderConfigError, find_cached_spec_path, get_provider


@lru_cache(maxsize=256)
def _path_pattern(template: str) -> re.Pattern[str]:
    """Turn an OpenAPI path template like /v1/customers/{customer} into a regex that
    also matches a concrete example path like /v1/customers/cus_123 - example code
    legitimately uses realistic IDs in place of {param} placeholders, and that must
    not be graded as citing a nonexistent endpoint."""
    parts = re.split(r"(\{[^}]+\})", template)
    pattern = "".join(
        r"[^/]+" if part.startswith("{") and part.endswith("}") else re.escape(part)
        for part in parts
    )
    return re.compile(f"^{pattern}$")


@dataclass(frozen=True)
class Truth:
    """The answer key for exactly one provider. Built from that provider's own
    machine-readable spec - the same parser ingestion uses - so it is objective and
    needs no hand-labeling. Always scoped to a single provider by construction; there is
    no cross-provider notion of "does this endpoint exist" at this level (see
    verify_endpoint/verify_parameter below for the multi-provider-aware entry points used
    by live citation verification)."""

    provider_id: str
    valid_endpoints: frozenset[tuple[str, str]]
    valid_params: dict[tuple[str, str], frozenset[str]]

    def _canonical(self, method: str | None, path: str) -> tuple[str, str] | None:
        for candidate_method, template in self.valid_endpoints:
            if method is not None and candidate_method != method.upper():
                continue
            if _path_pattern(template).match(path):
                return (candidate_method, template)
        return None

    def endpoint_exists(self, method: str | None, path: str) -> bool:
        return self._canonical(method, path) is not None

    def parameter_exists(self, method: str | None, path: str, name: str) -> bool:
        canonical = self._canonical(method, path)
        if canonical is None:
            return False
        return name in self.valid_params.get(canonical, frozenset())

    def params_for(self, endpoints: set[tuple[str, str]]) -> frozenset[str]:
        params: set[str] = set()
        for method, path in endpoints:
            canonical = self._canonical(method, path)
            if canonical is not None:
                params |= self.valid_params.get(canonical, frozenset())
        return frozenset(params)


def build_truth(
    provider_id: str, spec: dict[str, Any], path_prefixes: tuple[str, ...] | None = None
) -> Truth:
    endpoints = parse_spec(spec, path_prefixes=path_prefixes)
    valid_endpoints = frozenset((e.method, e.path) for e in endpoints)
    valid_params = {
        (e.method, e.path): frozenset(p.name for p in e.parameters) for e in endpoints
    }
    return Truth(provider_id=provider_id, valid_endpoints=valid_endpoints, valid_params=valid_params)


def load_truth(provider_id: str) -> Truth:
    """Reads whichever spec is on disk for this provider right now (its local `path`, or
    the cached download under data/specs/) and re-parses it fresh - no DB involved, so
    this works identically whether called from the API process or a one-shot CLI eval
    run. Raises FileNotFoundError if the provider has never been ingested (no cached
    spec yet) - callers on the live request path (cached_truth) turn that into "unknown
    provider, unverified" rather than an error; eval/CLI callers let it propagate, since
    running eval against a never-ingested provider is a real usage mistake worth failing
    loudly on."""
    provider = get_provider(provider_id)
    if provider.is_local:
        assert provider.path is not None  # is_local guarantees this
        text = Path(provider.path).read_text()
    else:
        cached = find_cached_spec_path(provider_id)
        if cached is None:
            raise FileNotFoundError(
                f"no cached spec for provider {provider_id!r} - run "
                f"`specpilot ingest --provider {provider_id}` first"
            )
        text = cached.read_text()

    spec = parse_spec_text(text, provider_id)
    return build_truth(provider_id, spec, provider.path_prefixes)


@cache
def cached_truth(provider_id: str) -> Truth | None:
    """Process-wide, per-provider cache (lru_cache is naturally keyed by the
    provider_id argument) for live request paths that need the answer key repeatedly but
    shouldn't re-read and re-parse a spec file on every request. Returns None - not an
    exception - for a provider that isn't configured or hasn't been ingested yet, so
    callers can treat "citation names a provider we don't know about" as unverified
    rather than a hard error."""
    try:
        return load_truth(provider_id)
    except (FileNotFoundError, ProviderConfigError):
        return None


def verify_endpoint(provider_id: str | None, method: str | None, path: str) -> bool:
    """The multi-provider-aware entry point live citation verification actually calls.
    A citation naming a provider that was never ingested (or no provider at all) is
    unverified, not an error - see cached_truth."""
    if provider_id is None:
        return False
    truth = cached_truth(provider_id)
    return truth is not None and truth.endpoint_exists(method, path)


def verify_parameter(provider_id: str | None, method: str | None, path: str, name: str) -> bool:
    if provider_id is None:
        return False
    truth = cached_truth(provider_id)
    return truth is not None and truth.parameter_exists(method, path, name)
