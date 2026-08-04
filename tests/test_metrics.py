from __future__ import annotations

from src.eval.metrics import (
    QuestionMetricInputs,
    average_cost,
    correct_refusal_rate,
    endpoint_accuracy,
    endpoint_recall,
    latency_percentile,
    mrr,
    parameter_hallucination_rate,
    recall_at_k,
)


def _make(
    *,
    unanswerable: bool = False,
    cited_endpoint_exists: list[bool] | None = None,
    cited_parameter_exists: list[bool] | None = None,
    expected_endpoint_count: int = 0,
    expected_endpoints_covered: int = 0,
    retrieved_ranks_of_expected: list[int] | None = None,
    refused: bool = False,
    latency_ms: float = 0.0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
) -> QuestionMetricInputs:
    return QuestionMetricInputs(
        question_id="q",
        split="dev",
        category="unanswerable" if unanswerable else "answerable",
        unanswerable=unanswerable,
        cited_endpoint_exists=cited_endpoint_exists or [],
        cited_parameter_exists=cited_parameter_exists or [],
        expected_endpoint_count=expected_endpoint_count,
        expected_endpoints_covered=expected_endpoints_covered,
        retrieved_ranks_of_expected=retrieved_ranks_of_expected or [],
        refused=refused,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )


def test_endpoint_accuracy_counts_citations_not_questions() -> None:
    results = [
        _make(cited_endpoint_exists=[True, True]),
        _make(cited_endpoint_exists=[False]),
    ]

    result = endpoint_accuracy(results)

    assert result.n == 3
    assert result.value == 2 / 3


def test_endpoint_accuracy_is_none_when_nothing_cited() -> None:
    result = endpoint_accuracy([_make(cited_endpoint_exists=[])])

    assert result.n == 0
    assert result.value is None


def test_parameter_hallucination_rate_is_fraction_that_do_not_exist() -> None:
    results = [_make(cited_parameter_exists=[True, False, False, True])]

    result = parameter_hallucination_rate(results)

    assert result.n == 4
    assert result.value == 0.5


def test_endpoint_recall_sums_across_questions() -> None:
    results = [
        _make(expected_endpoint_count=2, expected_endpoints_covered=1),
        _make(expected_endpoint_count=1, expected_endpoints_covered=1),
    ]

    result = endpoint_recall(results)

    assert result.n == 3
    assert result.value == 2 / 3


def test_recall_at_k_excludes_questions_with_no_expected_endpoint() -> None:
    results = [
        _make(expected_endpoint_count=1, retrieved_ranks_of_expected=[3]),
        _make(expected_endpoint_count=1, retrieved_ranks_of_expected=[]),
        _make(expected_endpoint_count=0),  # unanswerable-style, excluded
    ]

    result = recall_at_k(results)

    assert result.n == 2
    assert result.value == 0.5


def test_mrr_uses_best_rank_per_question() -> None:
    results = [
        _make(expected_endpoint_count=1, retrieved_ranks_of_expected=[3, 1]),  # best rank 1
        _make(expected_endpoint_count=1, retrieved_ranks_of_expected=[]),  # not found -> 0
    ]

    result = mrr(results)

    assert result.n == 2
    assert result.value == (1 / 1 + 0.0) / 2


def test_correct_refusal_rate_only_considers_unanswerable_questions() -> None:
    results = [
        _make(unanswerable=True, refused=True),
        _make(unanswerable=True, refused=False),
        _make(unanswerable=False, refused=False),  # answerable, ignored
    ]

    result = correct_refusal_rate(results)

    assert result.n == 2
    assert result.value == 0.5


def test_latency_percentile_p50_and_p95() -> None:
    results = [_make(latency_ms=ms) for ms in [100, 200, 300, 400, 500]]

    assert latency_percentile(results, 50) == 300
    assert latency_percentile(results, 95) == 500


def test_latency_percentile_empty_is_none() -> None:
    assert latency_percentile([], 50) is None


def test_average_cost() -> None:
    results = [_make(cost_usd=0.01), _make(cost_usd=0.03)]

    assert average_cost(results) == 0.02


def test_average_cost_empty_is_none() -> None:
    assert average_cost([]) is None
