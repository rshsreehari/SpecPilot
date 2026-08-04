from __future__ import annotations

from src.ingest.chunk import build_chunk_text
from src.ingest.parse import ParsedEndpoint, ParsedParameter


def test_chunk_contains_method_path_and_parameters() -> None:
    endpoint = ParsedEndpoint(
        method="GET",
        path="/v1/widgets",
        operation_id="GetWidgets",
        summary="List widgets",
        description="Returns a list of widgets.",
        tags=["Widgets"],
        parameters=[
            ParsedParameter(
                name="limit",
                location="query",
                type="integer",
                required=False,
                description="A limit on the number of objects to return.",
            )
        ],
    )

    text = build_chunk_text(endpoint)

    assert "GET /v1/widgets" in text
    assert "List widgets" in text
    assert "Returns a list of widgets." in text
    assert "limit" in text
    assert "A limit on the number of objects to return." in text


def test_chunk_without_parameters_has_no_parameters_section() -> None:
    endpoint = ParsedEndpoint(
        method="GET",
        path="/v1/widgets",
        operation_id="GetWidgets",
        summary="List widgets",
        description=None,
        tags=[],
        parameters=[],
    )

    text = build_chunk_text(endpoint)

    assert "Parameters:" not in text
