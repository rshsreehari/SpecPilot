from __future__ import annotations

import json
from pathlib import Path

from src.observability import (
    HALLUCINATION_RATE,
    QUERY_COUNT,
    TOOL_CALLS_TOTAL,
    record_query,
    record_tool_call,
    refresh_hallucination_gauge,
    render_metrics,
)


def test_record_query_increments_counter_and_histogram() -> None:
    before = QUERY_COUNT.labels(endpoint="query")._value.get()

    record_query("query", 0.5, prompt_tokens=100, completion_tokens=50)

    after = QUERY_COUNT.labels(endpoint="query")._value.get()
    assert after == before + 1


def test_record_tool_call_increments_counter() -> None:
    before = TOOL_CALLS_TOTAL.labels(tool="search_docs")._value.get()

    record_tool_call("search_docs")

    after = TOOL_CALLS_TOTAL.labels(tool="search_docs")._value.get()
    assert after == before + 1


def test_refresh_hallucination_gauge_reads_latest_report(tmp_path: Path) -> None:
    older = tmp_path / "20260101T000000Z.json"
    older.write_text(
        json.dumps(
            {
                "splits": {
                    "dev": {"with_retrieval": {"parameter_hallucination_rate": 0.9}}
                }
            }
        )
    )
    newer = tmp_path / "20260101T010000Z.json"
    newer.write_text(
        json.dumps(
            {
                "splits": {
                    "dev": {"with_retrieval": {"parameter_hallucination_rate": 0.25}}
                }
            }
        )
    )
    import os
    import time

    os.utime(older, (time.time() - 100, time.time() - 100))

    refresh_hallucination_gauge(tmp_path)

    assert HALLUCINATION_RATE._value.get() == 0.25


def test_refresh_hallucination_gauge_skips_baseline_modes(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "splits": {
                    "dev": {
                        "no_retrieval": {"parameter_hallucination_rate": 0.99},
                        "reranked": {"parameter_hallucination_rate": 0.1},
                    }
                }
            }
        )
    )

    refresh_hallucination_gauge(tmp_path)

    assert HALLUCINATION_RATE._value.get() == 0.1


def test_refresh_hallucination_gauge_missing_dir_does_not_raise(tmp_path: Path) -> None:
    refresh_hallucination_gauge(tmp_path / "does-not-exist")


def test_refresh_hallucination_gauge_malformed_json_does_not_raise(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json")

    refresh_hallucination_gauge(tmp_path)


def test_render_metrics_returns_prometheus_text_format() -> None:
    output = render_metrics()

    assert b"specpilot_query_total" in output
    assert b"# HELP" in output
    assert b"# TYPE" in output
