from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from src.agent.loop import run_agent
from src.agent.tools import AgentContext
from src.answer.mistral_client import MistralChatClient
from src.config import settings
from src.db import async_session_maker
from src.eval.grade import grade_question
from src.eval.metrics import QuestionMetricInputs
from src.eval.questions import Question, filter_split, load_questions
from src.eval.report import build_agent_report, render_agent_markdown
from src.eval.runner import (
    REPORTS_DIR,
    endpoint_lookups,
    grade_with_retrieval,
    timestamp_stamp,
    write_report,
)
from src.eval.truth import Truth, load_truth
from src.logging import get_logger
from src.retrieval.factory import build_retriever

logger = get_logger(__name__)


def _multi_step_questions(provider_id: str, split: str) -> list[Question]:
    return [
        q for q in filter_split(load_questions(provider_id), split) if q.category == "multi_step"
    ]


async def _grade_agent(
    question: Question,
    context: AgentContext,
    chat_client: MistralChatClient,
    truth: Truth,
    endpoint_id_by_method_path: dict[tuple[str, str], int],
    seed: int | None,
) -> tuple[QuestionMetricInputs, dict[str, Any]]:
    start = time.perf_counter()
    agent_result = await run_agent(question.question, context, chat_client, seed=seed)
    latency_ms = (time.perf_counter() - start) * 1000

    graded = grade_question(
        question_id=question.id,
        split=question.split,
        category=question.category,
        expected_endpoints=set(question.expected_endpoints),
        answer=agent_result.answer,
        retrieved_endpoint_ids_ranked=[],
        expected_endpoint_ids=set(),
        truth=truth,
        latency_ms=latency_ms,
        prompt_tokens=agent_result.prompt_tokens,
        completion_tokens=agent_result.completion_tokens,
        model=settings.mistral_model,
    )

    # wasted_call_rate: a tool call is wasted if none of the endpoints it surfaced ended
    # up among the endpoints the final answer actually cites - i.e. the agent looked
    # something up and then didn't use it.
    final_endpoint_ids = {
        endpoint_id_by_method_path[(e.method, e.path)]
        for e in graded.graded_endpoints
        if e.method is not None and (e.method, e.path) in endpoint_id_by_method_path
    }
    wasted = sum(
        1 for step in agent_result.trace if not set(step.endpoint_ids) & final_endpoint_ids
    )
    metrics = replace(
        graded.metrics, tool_call_count=len(agent_result.trace), wasted_tool_call_count=wasted
    )

    record = {
        "question_id": question.id,
        "provider": question.provider,
        "split": question.split,
        "category": question.category,
        "mode": "agent",
        "question": question.question,
        "answer": agent_result.answer.answer,
        "code_snippet": agent_result.answer.code_snippet,
        "citations": [c.model_dump() for c in agent_result.answer.citations],
        "trace": [step.model_dump() for step in agent_result.trace],
        "graded_endpoints": [
            {"method": e.method, "path": e.path} for e in graded.graded_endpoints
        ],
        "expected_endpoints": [
            {"method": m, "path": p} for m, p in sorted(question.expected_endpoints)
        ],
        "expected_endpoints_covered": graded.metrics.expected_endpoints_covered,
        "refused": graded.metrics.refused,
        "tool_call_count": len(agent_result.trace),
        "wasted_tool_call_count": wasted,
        "latency_ms": round(latency_ms, 1),
    }
    return metrics, record


async def run_agent_eval(
    provider_id: str, split: str = "all", seed: int | None = None, top_k: int | None = None
) -> dict[str, Any]:
    """Runs a provider's multi_step questions two ways: through the agent loop (which
    can chain search_docs / get_endpoint / list_parameters / find_related), and through
    the plain single-pass retrieval+answer path, for direct comparison. Does not touch
    grade.py/extract.py/truth.py/metrics.py's core logic - only adds the two
    agent-specific fields (tool_call_count, wasted_tool_call_count) that default to 0/0
    for every non-agent question, and reuses grade_question and grade_with_retrieval
    exactly as the single-pass runner does."""
    resolved_top_k = top_k or settings.top_k_default
    questions = _multi_step_questions(provider_id, split)
    truth = load_truth(provider_id)
    chat_client = MistralChatClient()

    agent_results: list[QuestionMetricInputs] = []
    single_pass_results: list[QuestionMetricInputs] = []
    question_records: list[dict[str, Any]] = []

    async with async_session_maker() as session:
        retriever = await build_retriever(settings.retrieval_strategy, session, provider_id)
        endpoint_id_by_method_path, endpoint_id_by_chunk_id = await endpoint_lookups(
            session, provider_id
        )
        context = AgentContext(
            session=session,
            retriever=retriever,
            top_k_default=resolved_top_k,
            provider_id=provider_id,
        )

        for question in questions:
            agent_metrics, agent_record = await _grade_agent(
                question, context, chat_client, truth, endpoint_id_by_method_path, seed
            )
            agent_results.append(agent_metrics)
            question_records.append(agent_record)

            single_graded, single_record = await grade_with_retrieval(
                question,
                resolved_top_k,
                retriever,
                chat_client,
                truth,
                endpoint_id_by_method_path,
                endpoint_id_by_chunk_id,
                seed,
                "single_pass",
            )
            single_pass_results.append(single_graded.metrics)
            question_records.append(single_record)

            logger.info(
                "agent_eval_question_done",
                provider=provider_id,
                question_id=question.id,
                split=question.split,
            )

    timestamp = datetime.now(UTC)
    report = build_agent_report(
        model=settings.mistral_model,
        timestamp=timestamp.isoformat(),
        agent=agent_results,
        single_pass=single_pass_results,
    )
    report["provider"] = provider_id
    report["questions"] = question_records
    stamp = timestamp_stamp(timestamp)
    write_report(
        REPORTS_DIR / f"agent-{provider_id}-{stamp}.json",
        REPORTS_DIR / f"agent-{provider_id}-{stamp}.md",
        report,
        render_agent_markdown(report),
    )
    return report
