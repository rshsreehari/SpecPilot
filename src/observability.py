from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from src.logging import get_logger

logger = get_logger(__name__)

registry = CollectorRegistry()

QUERY_COUNT = Counter(
    "specpilot_query_total",
    "Total number of query requests",
    ["endpoint"],
    registry=registry,
)
QUERY_LATENCY = Histogram(
    "specpilot_query_latency_seconds",
    "Query latency in seconds",
    ["endpoint"],
    registry=registry,
)
TOKENS_TOTAL = Counter(
    "specpilot_tokens_total",
    "Total Mistral tokens used",
    ["direction"],
    registry=registry,
)
TOOL_CALLS_TOTAL = Counter(
    "specpilot_tool_calls_total",
    "Total agent tool calls",
    ["tool"],
    registry=registry,
)
HALLUCINATION_RATE = Gauge(
    "specpilot_parameter_hallucination_rate",
    "parameter_hallucination_rate from the most recent eval report on disk",
    registry=registry,
)

REPORTS_DIR = Path("eval/reports")

# Baseline conditions to skip when picking which column/row of a report represents "the
# system's real answer" for the gauge - these exist specifically to score worse.
_BASELINE_MODES = {"no_retrieval", "single_pass"}


def record_query(
    endpoint: str, duration_seconds: float, prompt_tokens: int, completion_tokens: int
) -> None:
    QUERY_COUNT.labels(endpoint=endpoint).inc()
    QUERY_LATENCY.labels(endpoint=endpoint).observe(duration_seconds)
    TOKENS_TOTAL.labels(direction="prompt").inc(prompt_tokens)
    TOKENS_TOTAL.labels(direction="completion").inc(completion_tokens)


def record_tool_call(tool: str) -> None:
    TOOL_CALLS_TOTAL.labels(tool=tool).inc()


def _latest_report_path(reports_dir: Path) -> Path | None:
    if not reports_dir.is_dir():
        return None
    candidates = sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _extract_hallucination_rate(report: dict[str, Any]) -> float | None:
    splits = report.get("splits", {})
    for split_data in splits.values():
        for mode, metrics in split_data.items():
            if mode in _BASELINE_MODES:
                continue
            value = metrics.get("parameter_hallucination_rate")
            if value is not None:
                return float(value)
    return None


def refresh_hallucination_gauge(reports_dir: Path = REPORTS_DIR) -> None:
    path = _latest_report_path(reports_dir)
    if path is None:
        logger.warning("metrics_no_eval_report_found", reports_dir=str(reports_dir))
        return
    try:
        report = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("metrics_report_read_failed", path=str(path), error=str(error))
        return

    rate = _extract_hallucination_rate(report)
    if rate is not None:
        HALLUCINATION_RATE.set(rate)


def render_metrics() -> bytes:
    refresh_hallucination_gauge()
    return generate_latest(registry)
