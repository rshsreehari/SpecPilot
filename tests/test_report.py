from __future__ import annotations

from src.eval.metrics import QuestionMetricInputs
from src.eval.report import (
    build_agent_report,
    build_comparison_report,
    build_report,
    metrics_for,
    render_agent_markdown,
    render_comparison_markdown,
    render_markdown,
)


def _make(
    split: str = "dev",
    category: str = "answerable",
    cited_endpoint_exists: list[bool] | None = None,
    expected_endpoint_count: int = 1,
    expected_endpoints_covered: int = 1,
    retrieved_ranks_of_expected: list[int] | None = None,
    unanswerable: bool = False,
    refused: bool = False,
    tool_call_count: int = 0,
    wasted_tool_call_count: int = 0,
) -> QuestionMetricInputs:
    return QuestionMetricInputs(
        question_id="q",
        split=split,
        category=category,
        unanswerable=unanswerable,
        cited_endpoint_exists=cited_endpoint_exists if cited_endpoint_exists is not None else [True],
        cited_parameter_exists=[True],
        expected_endpoint_count=expected_endpoint_count,
        expected_endpoints_covered=expected_endpoints_covered,
        retrieved_ranks_of_expected=retrieved_ranks_of_expected or [1],
        refused=refused,
        latency_ms=100.0,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
        tool_call_count=tool_call_count,
        wasted_tool_call_count=wasted_tool_call_count,
    )


def test_metrics_for_empty_results_returns_zero_n() -> None:
    assert metrics_for([]) == {"n": 0}


def test_metrics_for_includes_n_alongside_every_ratio() -> None:
    metrics = metrics_for([_make(), _make(cited_endpoint_exists=[False])])

    assert metrics["n"] == 2
    assert metrics["endpoint_accuracy_n"] == 2
    assert metrics["endpoint_accuracy"] == 0.5


def test_metrics_for_includes_agent_fields() -> None:
    metrics = metrics_for([_make(tool_call_count=4, wasted_tool_call_count=1)])

    assert metrics["tool_calls_per_query"] == 4.0
    assert metrics["wasted_call_rate"] == 0.25
    assert metrics["wasted_call_rate_n"] == 4


def test_build_report_splits_dev_and_holdout_separately() -> None:
    report = build_report(
        model="mistral-large-latest",
        timestamp="2026-01-01T00:00:00Z",
        with_retrieval=[_make(split="dev"), _make(split="holdout")],
        no_retrieval=[_make(split="dev"), _make(split="holdout")],
    )

    assert set(report["splits"].keys()) == {"dev", "holdout"}
    assert "with_retrieval" in report["splits"]["dev"]
    assert "no_retrieval" in report["splits"]["dev"]


def test_render_markdown_includes_metric_rows_and_n() -> None:
    report = build_report(
        model="mistral-large-latest",
        timestamp="2026-01-01T00:00:00Z",
        with_retrieval=[_make()],
        no_retrieval=[_make(cited_endpoint_exists=[False])],
    )

    markdown = render_markdown(report)

    assert "# SpecPilot Evaluation Report" in markdown
    assert "## dev (n=1)" in markdown
    assert "endpoint_accuracy" in markdown
    assert "(n=1)" in markdown


def test_render_markdown_handles_missing_metric_gracefully() -> None:
    report = build_report(
        model="m", timestamp="t", with_retrieval=[_make()], no_retrieval=[]
    )

    markdown = render_markdown(report)

    assert "--" in markdown  # no_retrieval column has no data for this split


def test_build_comparison_report_has_one_row_per_strategy() -> None:
    report = build_comparison_report(
        model="m",
        timestamp="t",
        strategy_results={
            "no_retrieval": [_make()],
            "naive": [_make()],
            "reranked": [_make(cited_endpoint_exists=[False])],
        },
    )

    assert set(report["splits"]["dev"].keys()) == {"no_retrieval", "naive", "reranked"}


def test_render_comparison_markdown_lists_every_strategy() -> None:
    report = build_comparison_report(
        model="m",
        timestamp="t",
        strategy_results={"no_retrieval": [_make()], "naive": [_make()]},
    )

    markdown = render_comparison_markdown(report)

    assert "# SpecPilot Strategy Comparison" in markdown
    assert "| no_retrieval |" in markdown
    assert "| naive |" in markdown


def test_build_agent_report_has_agent_and_single_pass_rows() -> None:
    report = build_agent_report(
        model="m",
        timestamp="t",
        agent=[_make(tool_call_count=3)],
        single_pass=[_make()],
    )

    assert set(report["splits"]["dev"].keys()) == {"agent", "single_pass"}
    assert report["splits"]["dev"]["agent"]["tool_calls_per_query"] == 3.0
    assert report["splits"]["dev"]["single_pass"]["tool_calls_per_query"] == 0.0


def test_render_agent_markdown_includes_tool_call_metrics() -> None:
    report = build_agent_report(
        model="m",
        timestamp="t",
        agent=[_make(tool_call_count=2, wasted_tool_call_count=1)],
        single_pass=[_make()],
    )

    markdown = render_agent_markdown(report)

    assert "# SpecPilot Agent vs Single-Pass Comparison" in markdown
    assert "tool_calls_per_query" in markdown
    assert "wasted_call_rate" in markdown
