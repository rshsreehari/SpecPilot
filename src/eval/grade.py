from __future__ import annotations

from dataclasses import dataclass

from src.answer.schemas import AnswerResult, Citation
from src.eval.extract import ExtractedEndpoint, ExtractedEvidence, extract_evidence
from src.eval.metrics import QuestionMetricInputs
from src.eval.pricing import cost_usd
from src.eval.truth import Truth

# Mechanical (string-matching, not an LLM judge) signal for "this answer declines the
# question's premise" - phrases a model uses when the correct answer is no. Citations
# alone are not a reliable refusal signal: a well-grounded refusal can legitimately cite
# real endpoints as evidence for why something isn't possible (e.g. "prices are
# immutable, see POST /v1/prices to create a new one instead").
_REFUSAL_PHRASES = (
    "does not support",
    "doesn't support",
    "not supported",
    "cannot",
    "can not",
    "can't",
    "no endpoint",
    "not possible",
    "immutable",
    "does not provide",
    "does not describe",
    "not describe",
    "does not cover",
    "does not mention",
    "doesn't mention",
    "not available",
    "no direct",
    "not directly",
)


@dataclass(frozen=True)
class GradedQuestion:
    metrics: QuestionMetricInputs
    evidence: ExtractedEvidence
    graded_endpoints: list[ExtractedEndpoint]


def _endpoint_matches(cited: tuple[str | None, str], expected: tuple[str, str]) -> bool:
    method, path = cited
    expected_method, expected_path = expected
    if path != expected_path:
        return False
    return method is None or method == expected_method


def _looks_like_refusal(answer_text: str) -> bool:
    lowered = answer_text.lower()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


def _merge_with_citations(
    text_endpoints: list[ExtractedEndpoint], citations: list[Citation]
) -> list[ExtractedEndpoint]:
    """Union of endpoints found by scanning the answer/code text with the model's
    self-reported citations[]. Both must be graded: text-scanning catches endpoints the
    answer discusses but forgot to list in citations[], while citations[] catches the
    common case where a model states a citation without ever repeating its literal path
    in prose (typical of SDK-style answers) - text-only extraction silently missed that
    entire class of hallucination. Phase 5's UI puts a verified badge on every citation
    chip, so a hallucinated citation must be catchable even with no prose path mention."""
    merged: dict[str, str | None] = {e.path: e.method for e in text_endpoints}
    for citation in citations:
        if merged.get(citation.path) is None:
            merged[citation.path] = citation.method
    return [ExtractedEndpoint(method=method, path=path) for path, method in merged.items()]


def grade_question(
    *,
    question_id: str,
    split: str,
    category: str,
    expected_endpoints: set[tuple[str, str]],
    answer: AnswerResult,
    retrieved_endpoint_ids_ranked: list[int],
    expected_endpoint_ids: set[int],
    truth: Truth,
    latency_ms: float,
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
) -> GradedQuestion:
    """Mechanical, spec-driven grading. Endpoints are graded from the union of what the
    extractor finds in the raw answer/code text and what the model self-reports in
    citations[] - see _merge_with_citations. Parameters are graded from the code
    snippet only, per BUILD.md; a model could cite the right endpoint while its code
    uses a hallucinated parameter, and that mismatch is exactly what this project
    measures."""
    evidence = extract_evidence(answer.answer, answer.code_snippet)
    graded_endpoints = _merge_with_citations(evidence.endpoints, answer.citations)

    cited_endpoint_exists = [truth.endpoint_exists(e.method, e.path) for e in graded_endpoints]

    # Parameter ground truth is scoped to the endpoint(s) the answer actually engaged
    # with. Prefer endpoints with a known method; if none, fall back to the question's
    # expected endpoints rather than guessing.
    scope_endpoints = {
        (e.method, e.path) for e in graded_endpoints if e.method is not None
    } or expected_endpoints
    valid_params_in_scope = truth.params_for(scope_endpoints)
    cited_parameter_exists = [p in valid_params_in_scope for p in evidence.parameters]

    covered = sum(
        1
        for expected in expected_endpoints
        if any(_endpoint_matches((e.method, e.path), expected) for e in graded_endpoints)
    )

    retrieved_ranks_of_expected = [
        rank
        for rank, endpoint_id in enumerate(retrieved_endpoint_ids_ranked, start=1)
        if endpoint_id in expected_endpoint_ids
    ]

    metrics = QuestionMetricInputs(
        question_id=question_id,
        split=split,
        category=category,
        unanswerable=category == "unanswerable",
        cited_endpoint_exists=cited_endpoint_exists,
        cited_parameter_exists=cited_parameter_exists,
        expected_endpoint_count=len(expected_endpoints),
        expected_endpoints_covered=covered,
        retrieved_ranks_of_expected=retrieved_ranks_of_expected,
        refused=len(answer.citations) == 0 or _looks_like_refusal(answer.answer),
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd(model, prompt_tokens, completion_tokens),
    )
    return GradedQuestion(metrics=metrics, evidence=evidence, graded_endpoints=graded_endpoints)
