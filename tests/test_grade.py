from __future__ import annotations

from src.answer.schemas import AnswerResult, Citation
from src.eval.grade import grade_question
from src.eval.truth import Truth

_TRUTH = Truth(
    provider_id="stripe",
    valid_endpoints=frozenset({("POST", "/v1/prices"), ("POST", "/v1/prices/{price}")}),
    valid_params={
        ("POST", "/v1/prices"): frozenset({"currency", "unit_amount"}),
        ("POST", "/v1/prices/{price}"): frozenset({"active", "metadata"}),
    },
)


def test_well_grounded_refusal_counts_as_refused_even_with_citations() -> None:
    # A correct "no" answer can legitimately cite real endpoints as evidence for why
    # something isn't possible - it shouldn't be penalized for having citations.
    answer = AnswerResult(
        answer=(
            "You cannot directly change the currency of an existing price. The currency "
            "parameter is only available when creating a new price via POST /v1/prices."
        ),
        code_snippet=None,
        citations=[Citation(method="POST", path="/v1/prices", operation_id="PostPrices")],
        retrieved_chunk_ids=[1],
    )

    graded = grade_question(
        question_id="q036",
        split="dev",
        category="unanswerable",
        expected_endpoints=set(),
        answer=answer,
        retrieved_endpoint_ids_ranked=[],
        expected_endpoint_ids=set(),
        truth=_TRUTH,
        latency_ms=100.0,
        prompt_tokens=10,
        completion_tokens=10,
        model="mistral-large-latest",
    )

    assert graded.metrics.refused is True


def test_confident_answer_with_no_refusal_language_is_not_refused() -> None:
    answer = AnswerResult(
        answer="Create a price with POST /v1/prices.",
        code_snippet=None,
        citations=[Citation(method="POST", path="/v1/prices", operation_id="PostPrices")],
        retrieved_chunk_ids=[1],
    )

    graded = grade_question(
        question_id="q021",
        split="dev",
        category="answerable",
        expected_endpoints={("POST", "/v1/prices")},
        answer=answer,
        retrieved_endpoint_ids_ranked=[],
        expected_endpoint_ids=set(),
        truth=_TRUTH,
        latency_ms=100.0,
        prompt_tokens=10,
        completion_tokens=10,
        model="mistral-large-latest",
    )

    assert graded.metrics.refused is False


def test_parameter_hallucination_scoped_to_cited_endpoint() -> None:
    answer = AnswerResult(
        answer="Create a price with POST /v1/prices.",
        code_snippet='stripe.Price.create(currency="usd", nonexistent_field="x")',
        citations=[Citation(method="POST", path="/v1/prices", operation_id="PostPrices")],
        retrieved_chunk_ids=[1],
    )

    graded = grade_question(
        question_id="q021",
        split="dev",
        category="answerable",
        expected_endpoints={("POST", "/v1/prices")},
        answer=answer,
        retrieved_endpoint_ids_ranked=[],
        expected_endpoint_ids=set(),
        truth=_TRUTH,
        latency_ms=100.0,
        prompt_tokens=10,
        completion_tokens=10,
        model="mistral-large-latest",
    )

    # currency is valid for POST /v1/prices, nonexistent_field is not.
    assert sorted(graded.metrics.cited_parameter_exists) == [False, True]


def test_hallucinated_citation_is_caught_even_with_no_prose_mention() -> None:
    # SDK-style answers often never repeat a literal REST path in prose - the model's
    # own self-reported citations[] must still be checked against the spec, or a
    # hallucinated endpoint sails through ungraded (the bug this test guards against).
    answer = AnswerResult(
        answer="Use the transfers API to move funds between accounts.",
        code_snippet="stripe.Transfer.create(amount=100, currency='usd')",
        citations=[
            Citation(method="POST", path="/v1/transfers", operation_id="create_transfer")
        ],
        retrieved_chunk_ids=[],
    )

    graded = grade_question(
        question_id="q039",
        split="dev",
        category="unanswerable",
        expected_endpoints=set(),
        answer=answer,
        retrieved_endpoint_ids_ranked=[],
        expected_endpoint_ids=set(),
        truth=_TRUTH,
        latency_ms=100.0,
        prompt_tokens=10,
        completion_tokens=10,
        model="mistral-large-latest",
    )

    assert {(e.method, e.path) for e in graded.graded_endpoints} == {
        ("POST", "/v1/transfers")
    }
    assert graded.metrics.cited_endpoint_exists == [False]
