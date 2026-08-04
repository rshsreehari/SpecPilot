from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import yaml

from src.logging import get_logger
from src.providers import ProviderConfig, spec_cache_path

logger = get_logger(__name__)


class SpecFormatError(ValueError):
    """Raised when a spec can't be parsed as JSON or YAML, or is Swagger 2.0."""


class SpecDownloadError(ValueError):
    """Raised when a remote spec cannot be fetched safely and completely."""


MAX_SPEC_BYTES = 50 * 1024 * 1024


def parse_spec_text(text: str, provider_id: str) -> dict[str, Any]:
    """Detect JSON vs YAML by content, never by file extension or URL suffix - some
    providers serve YAML from a path that ends in .json. JSON is valid YAML, so trying
    the faster json.loads first and falling back to yaml.safe_load on failure correctly
    handles both without ever needing to know which one we were given."""
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        try:
            spec = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise SpecFormatError(
                f"provider {provider_id!r}: spec is neither valid JSON nor valid YAML"
            ) from error
    if not isinstance(spec, dict):
        raise SpecFormatError(f"provider {provider_id!r}: parsed spec is not a JSON/YAML object")
    _reject_swagger_2(spec, provider_id)
    openapi_version = spec.get("openapi")
    if not isinstance(openapi_version, str):
        raise SpecFormatError(
            f"provider {provider_id!r}: document is missing the required OpenAPI 3.x "
            "'openapi' version field"
        )
    if not isinstance(spec.get("paths"), dict):
        raise SpecFormatError(
            f"provider {provider_id!r}: OpenAPI document is missing a valid 'paths' object"
        )
    return spec


def _reject_swagger_2(spec: dict[str, Any], provider_id: str) -> None:
    if "swagger" in spec and "openapi" not in spec:
        raise SpecFormatError(
            f"provider {provider_id!r}: this spec declares swagger: {spec.get('swagger')!r} "
            "(Swagger 2.0). SpecPilot only supports OpenAPI 3.x - Swagger 2.0 is out of scope."
        )
    openapi_version = spec.get("openapi")
    supported = isinstance(openapi_version, str) and (
        openapi_version in {"3.0", "3.1"}
        or openapi_version.startswith(("3.0.", "3.1."))
    )
    if isinstance(openapi_version, str) and not supported:
        raise SpecFormatError(
            f"provider {provider_id!r}: unsupported openapi version {openapi_version!r}, "
            "only OpenAPI 3.0 and 3.1 are supported"
        )


def _cache_ext(text: str) -> str:
    try:
        json.loads(text)
        return "json"
    except json.JSONDecodeError:
        return "yaml"


async def fetch_spec(provider: ProviderConfig, refresh: bool = False) -> dict[str, Any]:
    """Loads a provider's spec from a local path, or downloads it (caching to
    data/specs/<id>.<ext>, reused on later calls unless refresh=True)."""
    if provider.is_local:
        assert provider.path is not None  # is_local guarantees this
        text = await asyncio.to_thread(Path(provider.path).read_text)
        return await asyncio.to_thread(parse_spec_text, text, provider.id)

    cached = None if refresh else _find_cached(provider.id)
    if cached is not None:
        logger.info("spec_cache_hit", provider=provider.id, path=str(cached))
        text = await asyncio.to_thread(cached.read_text)
        return await asyncio.to_thread(parse_spec_text, text, provider.id)

    logger.info("spec_downloading", provider=provider.id, url=provider.url)
    assert provider.url is not None  # not is_local guarantees this
    text = await download_spec_text(provider.url, provider.id)

    ext = _cache_ext(text)
    cache_path = spec_cache_path(provider.id, ext)
    await asyncio.to_thread(cache_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(cache_path.write_text, text)
    logger.info("spec_cached", provider=provider.id, path=str(cache_path))

    return await asyncio.to_thread(parse_spec_text, text, provider.id)


async def download_spec_text(
    url: str,
    provider_id: str,
    *,
    timeout_seconds: float = 30.0,
    max_bytes: int = MAX_SPEC_BYTES,
) -> str:
    """Downloads a URL with the same limits used by preview and ingestion.

    The response is streamed and counted before decoding so a server cannot bypass the
    50 MB cap by omitting or lying in Content-Length.
    """
    if not url.startswith(("http://", "https://")):
        raise SpecDownloadError(
            f"provider {provider_id!r}: spec URL must start with http:// or https://"
        )

    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=True, max_redirects=3
        ) as client, client.stream("GET", url) as response:
            response.raise_for_status()
            declared_length = response.headers.get("content-length")
            if declared_length and int(declared_length) > max_bytes:
                raise SpecDownloadError(
                    f"provider {provider_id!r}: spec is larger than the 50 MB limit"
                )
            chunks: list[bytes] = []
            received = 0
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > max_bytes:
                    raise SpecDownloadError(
                        f"provider {provider_id!r}: spec is larger than the 50 MB limit"
                    )
                chunks.append(chunk)
    except SpecDownloadError:
        raise
    except httpx.TooManyRedirects as error:
        raise SpecDownloadError(
            f"provider {provider_id!r}: spec URL followed more than 3 redirects"
        ) from error
    except httpx.TimeoutException as error:
        raise SpecDownloadError(
            f"provider {provider_id!r}: spec download timed out after 30 seconds"
        ) from error
    except httpx.HTTPStatusError as error:
        raise SpecDownloadError(
            f"provider {provider_id!r}: spec URL returned HTTP {error.response.status_code}"
        ) from error
    except httpx.HTTPError as error:
        raise SpecDownloadError(
            f"provider {provider_id!r}: could not download spec: {error}"
        ) from error
    except ValueError as error:
        raise SpecDownloadError(
            f"provider {provider_id!r}: spec URL returned an invalid Content-Length"
        ) from error

    try:
        return b"".join(chunks).decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise SpecDownloadError(
            f"provider {provider_id!r}: spec response is not UTF-8 text"
        ) from error


def _find_cached(provider_id: str) -> Path | None:
    for ext in ("json", "yaml"):
        candidate = spec_cache_path(provider_id, ext)
        if candidate.is_file():
            return candidate
    return None
