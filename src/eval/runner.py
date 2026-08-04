from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.answer.mistral_client import MistralChatClient
from src.config import settings
from src.db import async_session_maker
from src.eval.grade import GradedQuestion, grade_question
from src.eval.harness import TimedAnswer, answer_with_retrieval, answer_without_retrieval
from src.eval.metrics import QuestionMetricInputs
from src.eval.questions import Question, filter_split, load_questions
from src.eval.report import (
    build_comparison_report,
    build_report,
    render_comparison_markdown,
    render_markdown,
)
from src.eval.truth import Truth, load_truth
from src.logging import get_logger
from src.models import Chunk, Endpoint
from src.providers import get_provider, load_providers
from src.retrieval.base import Retriever
from src.retrieval.factory import STRATEGIES, build_retriever

logger = get_logger(__name__)

REPORTS_DIR = Path("eval/reports")


async def endpoint_lookups(
    session: AsyncSession, provider_id: str
) -> tuple[dict[tuple[str, str], int], dict[int, int]]:
    endpoint_rows = (
        await session.execute(
            select(Endpoint.id, Endpoint.method, Endpoint.path).where(
                Endpoint.provider_id == provider_id
            )
        )
    ).all()
    endpoint_id_by_method_path = {(row.method, row.path): row.id for row in endpoint_rows}

    chunk_rows = (
        await session.execute(
            select(Chunk.id, Chunk.endpoint_id).where(Chunk.provider_id == provider_id)
        )
    ).all()
    endpoint_id_by_chunk_id = {row.id: row.endpoint_id for row in chunk_rows}

    return endpoint_id_by_method_path, endpoint_id_by_chunk_id


def record_question(question: Question, mode: str, timed: TimedAnswer, graded: GradedQuestion) -> dict[str, Any]:
    """Raw per-question detail, kept in the JSON report only (not the markdown table) so
    BUILD.md's "check the extractor by hand on three answers" step has something to check
    against without re-running the eval."""
    result = timed.generated.result
    return {
        "question_id": question.id,
        "provider": question.provider,
        "split": question.split,
        "category": question.category,
        "mode": mode,
        "question": question.question,
        "answer": result.answer,
        "code_snippet": result.code_snippet,
        "citations": [c.model_dump() for c in result.citations],
        "retrieved_chunk_ids": result.retrieved_chunk_ids,
        "graded_endpoints": [
            {"method": e.method, "path": e.path} for e in graded.graded_endpoints
        ],
        "text_only_extracted_endpoints": [
            {"method": e.method, "path": e.path} for e in graded.evidence.endpoints
        ],
        "extracted_parameters": sorted(graded.evidence.parameters),
        "expected_endpoints": [
            {"method": m, "path": p} for m, p in sorted(question.expected_endpoints)
        ],
        "expected_endpoints_covered": graded.metrics.expected_endpoints_covered,
        "refused": graded.metrics.refused,
        "latency_ms": round(timed.latency_ms, 1),
    }


async def grade_with_retrieval(
    question: Question,
    top_k: int,
    retriever: Retriever,
    chat_client: MistralChatClient,
    truth: Truth,
    endpoint_id_by_method_path: dict[tuple[str, str], int],
    endpoint_id_by_chunk_id: dict[int, int],
    seed: int | None,
    mode_label: str,
) -> tuple[GradedQuestion, dict[str, Any]]:
    expected_endpoint_ids = {
        endpoint_id_by_method_path[ep]
        for ep in question.expected_endpoints
        if ep in endpoint_id_by_method_path
    }

    timed = await answer_with_retrieval(
        question.question, top_k, retriever, chat_client, seed=seed, provider_id=question.provider
    )
    retrieved_endpoint_ids_ranked = [
        endpoint_id_by_chunk_id[chunk_id]
        for chunk_id in timed.generated.result.retrieved_chunk_ids
        if chunk_id in endpoint_id_by_chunk_id
    ]
    graded = grade_question(
        question_id=question.id,
        split=question.split,
        category=question.category,
        expected_endpoints=set(question.expected_endpoints),
        answer=timed.generated.result,
        retrieved_endpoint_ids_ranked=retrieved_endpoint_ids_ranked,
        expected_endpoint_ids=expected_endpoint_ids,
        truth=truth,
        latency_ms=timed.latency_ms,
        prompt_tokens=timed.generated.prompt_tokens,
        completion_tokens=timed.generated.completion_tokens,
        model=settings.mistral_model,
    )
    return graded, record_question(question, mode_label, timed, graded)


async def grade_no_retrieval(
    question: Question,
    chat_client: MistralChatClient,
    truth: Truth,
    seed: int | None,
    provider_name: str = "the",
) -> tuple[GradedQuestion, dict[str, Any]]:
    timed = await answer_without_retrieval(
        question.question,
        chat_client,
        seed=seed,
        provider_name=provider_name,
        provider_id=question.provider,
    )
    graded = grade_question(
        question_id=question.id,
        split=question.split,
        category=question.category,
        expected_endpoints=set(question.expected_endpoints),
        answer=timed.generated.result,
        retrieved_endpoint_ids_ranked=[],
        expected_endpoint_ids=set(),
        truth=truth,
        latency_ms=timed.latency_ms,
        prompt_tokens=timed.generated.prompt_tokens,
        completion_tokens=timed.generated.completion_tokens,
        model=settings.mistral_model,
    )
    return graded, record_question(question, "no_retrieval", timed, graded)


async def _collect_eval_results(
    provider_id: str,
    split: str,
    seed: int | None,
    top_k: int,
    strategy: str,
) -> tuple[list[QuestionMetricInputs], list[QuestionMetricInputs], list[dict[str, Any]]]:
    questions = filter_split(load_questions(provider_id), split)
    truth = load_truth(provider_id)
    provider_name = get_provider(provider_id).name
    chat_client = MistralChatClient()

    results_with_retrieval: list[QuestionMetricInputs] = []
    results_no_retrieval: list[QuestionMetricInputs] = []
    question_records: list[dict[str, Any]] = []

    async with async_session_maker() as session:
        retriever = await build_retriever(strategy, session, provider_id)
        endpoint_id_by_method_path, endpoint_id_by_chunk_id = await endpoint_lookups(
            session, provider_id
        )

        for question in questions:
            graded_with, record_with = await grade_with_retrieval(
                question,
                top_k,
                retriever,
                chat_client,
                truth,
                endpoint_id_by_method_path,
                endpoint_id_by_chunk_id,
                seed,
                strategy,
            )
            graded_without, record_without = await grade_no_retrieval(
                question, chat_client, truth, seed, provider_name
            )
            results_with_retrieval.append(graded_with.metrics)
            results_no_retrieval.append(graded_without.metrics)
            question_records.append(record_with)
            question_records.append(record_without)
            logger.info(
                "eval_question_done", provider=provider_id, question_id=question.id, split=question.split
            )

    return results_with_retrieval, results_no_retrieval, question_records


async def run_eval(
    provider_id: str,
    split: str = "all",
    seed: int | None = None,
    top_k: int | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    resolved_strategy = strategy or settings.retrieval_strategy
    resolved_top_k = top_k or settings.top_k_default

    results_with_retrieval, results_no_retrieval, question_records = await _collect_eval_results(
        provider_id, split, seed, resolved_top_k, resolved_strategy
    )

    timestamp = datetime.now(UTC)
    report = build_report(
        model=settings.mistral_model,
        timestamp=timestamp.isoformat(),
        with_retrieval=results_with_retrieval,
        no_retrieval=results_no_retrieval,
    )
    report["provider"] = provider_id
    report["strategy"] = resolved_strategy
    report["questions"] = question_records
    stamp = timestamp_stamp(timestamp)
    write_report(
        REPORTS_DIR / f"{provider_id}-{stamp}.json",
        REPORTS_DIR / f"{provider_id}-{stamp}.md",
        report,
        render_markdown(report),
    )
    return report


async def run_eval_all_providers(
    split: str = "all", seed: int | None = None, strategy: str | None = None
) -> dict[str, Any]:
    """Runs eval separately for every configured provider, then pools every provider's
    raw per-question metrics into one combined table - never averages already-computed
    per-provider percentages together, which would weight a 10-question provider the
    same as a 40-question one. The per-provider breakdown is always kept alongside the
    combined numbers, never replaced by them - the specs differ enough that a pooled
    average alone would hide the actual, interesting result (which strategy wins, and by
    how much, can differ by provider)."""
    resolved_strategy = strategy or settings.retrieval_strategy
    resolved_top_k = settings.top_k_default
    providers = load_providers()

    per_provider_reports: dict[str, dict[str, Any]] = {}
    pooled_with: list[QuestionMetricInputs] = []
    pooled_without: list[QuestionMetricInputs] = []

    for provider_id in providers:
        results_with, results_without, question_records = await _collect_eval_results(
            provider_id, split, seed, resolved_top_k, resolved_strategy
        )
        pooled_with.extend(results_with)
        pooled_without.extend(results_without)
        provider_report = build_report(
            model=settings.mistral_model,
            timestamp=datetime.now(UTC).isoformat(),
            with_retrieval=results_with,
            no_retrieval=results_without,
        )
        provider_report["provider"] = provider_id
        provider_report["questions"] = question_records
        per_provider_reports[provider_id] = provider_report

    timestamp = datetime.now(UTC)
    combined = build_report(
        model=settings.mistral_model,
        timestamp=timestamp.isoformat(),
        with_retrieval=pooled_with,
        no_retrieval=pooled_without,
    )
    report = {
        "timestamp": timestamp.isoformat(),
        "model": settings.mistral_model,
        "strategy": resolved_strategy,
        "providers": list(providers),
        "per_provider": per_provider_reports,
        "splits": combined["splits"],
    }
    stamp = timestamp_stamp(timestamp)
    write_report(
        REPORTS_DIR / f"all-providers-{stamp}.json",
        REPORTS_DIR / f"all-providers-{stamp}.md",
        report,
        render_all_providers_markdown(report),
    )
    return report


async def run_compare(
    provider_id: str, split: str = "all", seed: int | None = None, top_k: int | None = None
) -> dict[str, Any]:
    resolved_top_k = top_k or settings.top_k_default
    questions = filter_split(load_questions(provider_id), split)
    truth = load_truth(provider_id)
    provider_name = get_provider(provider_id).name
    chat_client = MistralChatClient()

    strategy_results: dict[str, list[QuestionMetricInputs]] = {
        "no_retrieval": [],
        **{s: [] for s in STRATEGIES},
    }
    question_records: list[dict[str, Any]] = []

    async with async_session_maker() as session:
        endpoint_id_by_method_path, endpoint_id_by_chunk_id = await endpoint_lookups(
            session, provider_id
        )
        retrievers = {s: await build_retriever(s, session, provider_id) for s in STRATEGIES}

        for question in questions:
            graded_without, record_without = await grade_no_retrieval(
                question, chat_client, truth, seed, provider_name
            )
            strategy_results["no_retrieval"].append(graded_without.metrics)
            question_records.append(record_without)

            for strategy_name, retriever in retrievers.items():
                graded_with, record_with = await grade_with_retrieval(
                    question,
                    resolved_top_k,
                    retriever,
                    chat_client,
                    truth,
                    endpoint_id_by_method_path,
                    endpoint_id_by_chunk_id,
                    seed,
                    strategy_name,
                )
                strategy_results[strategy_name].append(graded_with.metrics)
                question_records.append(record_with)

            logger.info(
                "compare_question_done", provider=provider_id, question_id=question.id, split=question.split
            )

    timestamp = datetime.now(UTC)
    report = build_comparison_report(
        model=settings.mistral_model,
        timestamp=timestamp.isoformat(),
        strategy_results=strategy_results,
    )
    report["provider"] = provider_id
    report["questions"] = question_records
    stamp = timestamp_stamp(timestamp)
    write_report(
        REPORTS_DIR / f"comparison-{provider_id}-{stamp}.json",
        REPORTS_DIR / f"comparison-{provider_id}-{stamp}.md",
        report,
        render_comparison_markdown(report),
    )
    return report


async def run_compare_all_providers(split: str = "all", seed: int | None = None) -> dict[str, Any]:
    """Same pooling principle as run_eval_all_providers: each provider's comparison runs
    independently (each strategy's retriever, and BM25's index in particular, stays
    scoped to that one provider - see retrieval/bm25.py), then every provider's
    per-question metrics for a given strategy are pooled for the combined row. Per-
    provider tables are always kept alongside so "reranked wins by 8 points on Stripe
    but only 2 on GitHub" - a real, more interesting finding than either number alone -
    stays visible."""
    top_k = settings.top_k_default
    providers = load_providers()

    per_provider_reports: dict[str, dict[str, Any]] = {}
    pooled: dict[str, list[QuestionMetricInputs]] = {"no_retrieval": [], **{s: [] for s in STRATEGIES}}

    for provider_id in providers:
        questions = filter_split(load_questions(provider_id), split)
        truth = load_truth(provider_id)
        provider_name = get_provider(provider_id).name
        chat_client = MistralChatClient()
        strategy_results: dict[str, list[QuestionMetricInputs]] = {
            "no_retrieval": [],
            **{s: [] for s in STRATEGIES},
        }
        question_records: list[dict[str, Any]] = []

        async with async_session_maker() as session:
            endpoint_id_by_method_path, endpoint_id_by_chunk_id = await endpoint_lookups(
                session, provider_id
            )
            retrievers = {s: await build_retriever(s, session, provider_id) for s in STRATEGIES}

            for question in questions:
                graded_without, record_without = await grade_no_retrieval(
                    question, chat_client, truth, seed, provider_name
                )
                strategy_results["no_retrieval"].append(graded_without.metrics)
                question_records.append(record_without)

                for strategy_name, retriever in retrievers.items():
                    graded_with, record_with = await grade_with_retrieval(
                        question,
                        top_k,
                        retriever,
                        chat_client,
                        truth,
                        endpoint_id_by_method_path,
                        endpoint_id_by_chunk_id,
                        seed,
                        strategy_name,
                    )
                    strategy_results[strategy_name].append(graded_with.metrics)
                    question_records.append(record_with)

        for key, values in strategy_results.items():
            pooled[key].extend(values)
        provider_report = build_comparison_report(
            model=settings.mistral_model,
            timestamp=datetime.now(UTC).isoformat(),
            strategy_results=strategy_results,
        )
        provider_report["provider"] = provider_id
        provider_report["questions"] = question_records
        per_provider_reports[provider_id] = provider_report

    timestamp = datetime.now(UTC)
    combined = build_comparison_report(
        model=settings.mistral_model, timestamp=timestamp.isoformat(), strategy_results=pooled
    )
    report = {
        "timestamp": timestamp.isoformat(),
        "model": settings.mistral_model,
        "providers": list(providers),
        "per_provider": per_provider_reports,
        "splits": combined["splits"],
    }
    stamp = timestamp_stamp(timestamp)
    write_report(
        REPORTS_DIR / f"comparison-all-providers-{stamp}.json",
        REPORTS_DIR / f"comparison-all-providers-{stamp}.md",
        report,
        render_all_providers_comparison_markdown(report),
    )
    return report


def render_all_providers_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SpecPilot Evaluation - All Providers",
        "",
        f"Model: {report['model']}    Generated: {report['timestamp']}",
        f"Providers: {', '.join(report['providers'])}",
        "",
        "## Combined (pooled across all providers)",
        "",
    ]
    for split, data in report["splits"].items():
        lines.append(f"### {split} (n={data.get('with_retrieval', {}).get('n', 0)})")
        lines.append(f"with_retrieval: {data.get('with_retrieval')}")
        lines.append(f"no_retrieval: {data.get('no_retrieval')}")
        lines.append("")
    lines.append("## Per-provider breakdown")
    lines.append("")
    for provider_id, provider_report in report["per_provider"].items():
        lines.append(f"### {provider_id}")
        lines.append(render_markdown(provider_report))
    return "\n".join(lines)


def render_all_providers_comparison_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SpecPilot Strategy Comparison - All Providers",
        "",
        f"Model: {report['model']}    Generated: {report['timestamp']}",
        f"Providers: {', '.join(report['providers'])}",
        "",
        "## Combined (pooled across all providers)",
        "",
    ]
    for split, strategies in report["splits"].items():
        lines.append(f"### {split}")
        for strategy_name, metrics in strategies.items():
            lines.append(f"{strategy_name}: {metrics}")
        lines.append("")
    lines.append("## Per-provider breakdown")
    lines.append("")
    for provider_id, provider_report in report["per_provider"].items():
        lines.append(f"### {provider_id}")
        lines.append(render_comparison_markdown(provider_report))
    return "\n".join(lines)


def timestamp_stamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def write_report(json_path: Path, md_path: Path, report: dict[str, Any], markdown: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(markdown)
    logger.info("eval_report_written", json_path=str(json_path), md_path=str(md_path))
