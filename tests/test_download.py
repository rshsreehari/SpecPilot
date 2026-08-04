from __future__ import annotations

import json

import pytest

from src.ingest.download import SpecFormatError, parse_spec_text


def test_parse_spec_text_detects_json_by_content() -> None:
    text = json.dumps({"openapi": "3.0.0", "paths": {}})

    spec = parse_spec_text(text, "test")

    assert spec["openapi"] == "3.0.0"


def test_parse_spec_text_detects_yaml_by_content() -> None:
    text = "openapi: 3.1.0\npaths: {}\n"

    spec = parse_spec_text(text, "test")

    assert spec["openapi"] == "3.1.0"


def test_parse_spec_text_rejects_swagger_2() -> None:
    text = json.dumps({"swagger": "2.0", "paths": {}})

    with pytest.raises(SpecFormatError, match="Swagger 2.0"):
        parse_spec_text(text, "legacy-provider")


def test_parse_spec_text_rejects_unsupported_openapi_version() -> None:
    text = json.dumps({"openapi": "2.5.0", "paths": {}})

    with pytest.raises(SpecFormatError, match="unsupported openapi version"):
        parse_spec_text(text, "test")


def test_parse_spec_text_rejects_future_openapi_32() -> None:
    text = json.dumps({"openapi": "3.2.0", "paths": {}})

    with pytest.raises(SpecFormatError, match="only OpenAPI 3.0 and 3.1"):
        parse_spec_text(text, "test")


def test_parse_spec_text_rejects_garbage() -> None:
    with pytest.raises(SpecFormatError, match="neither valid JSON nor valid YAML"):
        parse_spec_text(":::not valid:::\n\tbad indent", "test")


def test_parse_spec_text_rejects_non_object_top_level() -> None:
    with pytest.raises(SpecFormatError, match="not a JSON/YAML object"):
        parse_spec_text(json.dumps([1, 2, 3]), "test")


def test_parse_spec_text_accepts_openapi_3_with_no_swagger_key() -> None:
    text = json.dumps({"openapi": "3.0.3", "paths": {"/x": {}}})

    spec = parse_spec_text(text, "test")

    assert spec["paths"] == {"/x": {}}
