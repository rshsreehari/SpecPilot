from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricResult:
    value: float | None
    n: int


@dataclass(frozen=True)
class QuestionMetricInputs:
    """Precomputed per-question grading facts. Deliberately holds only booleans/counts,
    not the spec or the raw answer, so the metric functions below are pure math and
    testable on synthetic data without touching the DB or the extractor."""

    question_id: str
    split: str
    category: str
    unanswerable: bool
    cited_endpoint_exists: list[bool]
    cited_parameter_exists: list[bool]
    expected_endpoint_count: int
    expected_endpoints_covered: int
    retrieved_ranks_of_expected: list[int]
    refused: bool
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    tool_call_count: int = 0
    wasted_tool_call_count: int = 0


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _ratio_float(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def endpoint_accuracy(results: list[QuestionMetricInputs]) -> MetricResult:
    """Cited endpoints that exist in the spec / total cited."""
    total = sum(len(r.cited_endpoint_exists) for r in results)
    correct = sum(sum(r.cited_endpoint_exists) for r in results)
    return MetricResult(_ratio(correct, total), total)


def parameter_hallucination_rate(results: list[QuestionMetricInputs]) -> MetricResult:
    """Params used that do not exist for the cited endpoint(s) / total params used."""
    total = sum(len(r.cited_parameter_exists) for r in results)
    hallucinated = sum(sum(not exists for exists in r.cited_parameter_exists) for r in results)
    return MetricResult(_ratio(hallucinated, total), total)


def endpoint_recall(results: list[QuestionMetricInputs]) -> MetricResult:
    """Expected endpoints that were cited / expected endpoints."""
    total = sum(r.expected_endpoint_count for r in results)
    covered = sum(r.expected_endpoints_covered for r in results)
    return MetricResult(_ratio(covered, total), total)


def recall_at_k(results: list[QuestionMetricInputs]) -> MetricResult:
    """Was a chunk from an expected endpoint in the retrieved set, over questions that
    have an expected endpoint (unanswerable questions have none and are excluded)."""
    eligible = [r for r in results if r.expected_endpoint_count > 0]
    hits = sum(1 for r in eligible if r.retrieved_ranks_of_expected)
    return MetricResult(_ratio(hits, len(eligible)), len(eligible))


def mrr(results: list[QuestionMetricInputs]) -> MetricResult:
    """Mean reciprocal rank of the first retrieved chunk from an expected endpoint."""
    eligible = [r for r in results if r.expected_endpoint_count > 0]
    total_reciprocal = sum(
        1 / min(r.retrieved_ranks_of_expected) if r.retrieved_ranks_of_expected else 0.0
        for r in eligible
    )
    return MetricResult(_ratio_float(total_reciprocal, len(eligible)), len(eligible))


def correct_refusal_rate(results: list[QuestionMetricInputs]) -> MetricResult:
    """Unanswerable questions correctly refused (citations left empty) / unanswerable."""
    unanswerable = [r for r in results if r.unanswerable]
    correct = sum(1 for r in unanswerable if r.refused)
    return MetricResult(_ratio(correct, len(unanswerable)), len(unanswerable))


def latency_percentile(results: list[QuestionMetricInputs], percentile: float) -> float | None:
    if not results:
        return None
    values = sorted(r.latency_ms for r in results)
    index = min(len(values) - 1, max(0, round(percentile / 100 * (len(values) - 1))))
    return values[index]


def average_cost(results: list[QuestionMetricInputs]) -> float | None:
    if not results:
        return None
    return sum(r.cost_usd for r in results) / len(results)


def tool_calls_per_query(results: list[QuestionMetricInputs]) -> MetricResult:
    """Average number of tool calls the agent made per question. n is the question
    count, not a ratio denominator - included for symmetry with the other metrics."""
    if not results:
        return MetricResult(None, 0)
    total_calls = sum(r.tool_call_count for r in results)
    return MetricResult(total_calls / len(results), len(results))


def wasted_call_rate(results: list[QuestionMetricInputs]) -> MetricResult:
    """Tool calls whose results are cited nowhere in the final answer / total tool
    calls. Only meaningful for agent-mode questions (tool_call_count > 0)."""
    total_calls = sum(r.tool_call_count for r in results)
    wasted = sum(r.wasted_tool_call_count for r in results)
    return MetricResult(_ratio(wasted, total_calls), total_calls)
