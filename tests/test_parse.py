from __future__ import annotations

import json
from pathlib import Path

from src.ingest.parse import parse_spec

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "small_spec.json"
EDGE_CASE_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "edge_case_spec.json"


def _load_spec() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _load_edge_case_spec() -> dict:
    return json.loads(EDGE_CASE_FIXTURE_PATH.read_text())


def test_resolves_valid_ref_and_skips_missing_ref() -> None:
    endpoints = parse_spec(_load_spec())

    get_widgets = next(e for e in endpoints if e.method == "GET")
    assert get_widgets.path == "/v1/widgets"
    assert get_widgets.operation_id == "GetWidgets"

    # MissingParam's $ref does not resolve; it must be skipped, not crash the parse.
    assert len(get_widgets.parameters) == 1
    assert get_widgets.parameters[0].name == "limit"
    assert get_widgets.parameters[0].type == "integer"
    assert get_widgets.parameters[0].required is False


def test_path_prefix_filters_endpoints() -> None:
    spec = _load_spec()

    assert parse_spec(spec, path_prefixes=("/v1/other",)) == []
    assert len(parse_spec(spec, path_prefixes=("/v1/widgets",))) == 2


def test_html_is_stripped_from_description() -> None:
    spec = _load_spec()
    spec["paths"]["/v1/widgets"]["get"]["description"] = "<p>Returns a list.</p>"

    endpoints = parse_spec(spec)
    get_widgets = next(e for e in endpoints if e.method == "GET")

    assert get_widgets.description == "Returns a list."


def test_request_body_properties_are_parsed_as_body_parameters() -> None:
    endpoints = parse_spec(_load_spec())

    post_widgets = next(e for e in endpoints if e.method == "POST")
    by_name = {p.name: p for p in post_widgets.parameters}

    assert set(by_name) == {"name", "color"}
    assert by_name["name"].location == "body"
    assert by_name["name"].required is True
    assert by_name["name"].type == "string"
    assert by_name["color"].required is False


def test_circular_ref_does_not_crash_or_hang() -> None:
    endpoints = parse_spec(_load_edge_case_spec())

    get_circular = next(e for e in endpoints if e.operation_id == "GetCircular")
    assert len(get_circular.parameters) == 1
    # The self-referential "child" property is never followed into an infinite loop;
    # the parameter itself still resolves (its own schema's top-level type is "object").
    assert get_circular.parameters[0].name == "circular"
    assert get_circular.parameters[0].type == "object"


def test_allof_composition_merges_all_branches_into_body_parameters() -> None:
    endpoints = parse_spec(_load_edge_case_spec())

    post_composed = next(e for e in endpoints if e.operation_id == "PostComposed")
    by_name = {p.name: p for p in post_composed.parameters}

    # base_id comes from the $ref'd allOf branch, extra from the inline branch - both
    # must be present, not just whichever branch happened to be resolved first.
    assert set(by_name) == {"base_id", "extra"}
    assert by_name["base_id"].required is True
    assert by_name["base_id"].type == "string"
    assert by_name["extra"].required is True


def test_missing_operation_id_is_synthesized_from_method_and_path() -> None:
    endpoints = parse_spec(_load_edge_case_spec())

    no_op_id = next(e for e in endpoints if e.path == "/v1/no-operation-id")
    assert no_op_id.operation_id == "get_v1_no_operation_id"


def test_path_level_parameters_are_shared_across_methods() -> None:
    endpoints = parse_spec(_load_edge_case_spec())

    get_shared = next(e for e in endpoints if e.operation_id == "GetShared")
    delete_shared = next(e for e in endpoints if e.operation_id == "DeleteShared")

    assert [p.name for p in get_shared.parameters] == ["id"]
    assert [p.name for p in delete_shared.parameters] == ["id"]
    assert get_shared.parameters[0].required is True


def test_openapi_31_array_type_prefers_first_non_null_type() -> None:
    endpoints = parse_spec(_load_edge_case_spec())

    get_nullable = next(e for e in endpoints if e.operation_id == "GetNullable")
    assert get_nullable.parameters[0].name == "maybe_count"
    assert get_nullable.parameters[0].type == "integer"


def test_multiple_media_types_are_unioned_into_body_parameters() -> None:
    endpoints = parse_spec(_load_edge_case_spec())

    post_multi = next(e for e in endpoints if e.operation_id == "PostMultiMedia")
    by_name = {p.name: p for p in post_multi.parameters}

    assert set(by_name) == {"json_field", "form_field"}
    assert by_name["json_field"].required is False
    assert by_name["form_field"].required is True
