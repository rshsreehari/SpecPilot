from __future__ import annotations

from src.api.app import _apply_screen_context


def test_no_context_returns_question_unchanged() -> None:
    result = _apply_screen_context("What's required here?", None, None, None)

    assert result == "What's required here?"


def test_context_present_prepends_endpoint_reference() -> None:
    result = _apply_screen_context(
        "What's required here?", "endpoint_detail", "POST", "/v1/subscriptions"
    )

    assert "POST /v1/subscriptions" in result
    assert result.endswith("What's required here?")


def test_partial_context_is_ignored() -> None:
    result = _apply_screen_context("q", "endpoint_detail", "POST", None)

    assert result == "q"
