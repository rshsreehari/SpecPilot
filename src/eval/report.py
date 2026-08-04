from __future__ import annotations

from typing import Any

from src.eval import metrics as metrics_mod
from src.eval.metrics import QuestionMetricInputs

_TABLE_METRICS: list[tuple[str, str, str]] = [
    ("endpoint_accuracy", "endpoint_accuracy", "pct"),
    ("parameter_hallucination_rate", "parameter_hallucination_rate", "pct"),
    ("endpoint_recall", "endpoint_recall", "pct"),
    ("recall_at_k", "recall_at_k", "pct"),
    ("mrr", "mrr", "float"),
    ("correct_refusal_rate", "correct_refusal_rate", "pct"),
    ("latency_p50_ms", "latency p50", "ms"),
    ("latency_p95_ms", "latency p95", "ms"),
    ("avg_prompt_tokens", "avg tokens in", "num"),
    ("avg_completion_tokens", "avg tokens out", "num"),
    ("avg_cost_usd", "cost per query", "cost"),
]


def metrics_for(results: list[QuestionMetricInputs]) -> dict[str, Any]:
    """Aggregate one mode's results into the report's metric dict. n is attached
    alongside every ratio metric (BUILD.md: "print n on every percentage") since each
    ratio can have a different denominator (e.g. recall_at_k excludes unanswerable
    questions, endpoint_accuracy counts citations not questions)."""
    if not results:
        return {"n": 0}

    accuracy = metrics_mod.endpoint_accuracy(results)
    hallucination = metrics_mod.parameter_hallucination_rate(results)
    recall = metrics_mod.endpoint_recall(results)
    recall_k = metrics_mod.recall_at_k(results)
    mrr_result = metrics_mod.mrr(results)
    refusal = metrics_mod.correct_refusal_rate(results)

    return {
        "n": len(results),
        "endpoint_accuracy": accuracy.value,
        "endpoint_accuracy_n": accuracy.n,
        "parameter_hallucination_rate": hallucination.value,
        "parameter_hallucination_rate_n": hallucination.n,
        "endpoint_recall": recall.value,
        "endpoint_recall_n": recall.n,
        "recall_at_k": recall_k.value,
        "recall_at_k_n": recall_k.n,
        "mrr": mrr_result.value,
        "mrr_n": mrr_result.n,
        "correct_refusal_rate": refusal.value,
        "correct_refusal_rate_n": refusal.n,
        "latency_p50_ms": metrics_mod.latency_percentile(results, 50),
        "latency_p95_ms": metrics_mod.latency_percentile(results, 95),
        "avg_prompt_tokens": sum(r.prompt_tokens for r in results) / len(results),
        "avg_completion_tokens": sum(r.completion_tokens for r in results) / len(results),
        "avg_cost_usd": metrics_mod.average_cost(results),
        "tool_calls_per_query": metrics_mod.tool_calls_per_query(results).value,
        "wasted_call_rate": metrics_mod.wasted_call_rate(results).value,
        "wasted_call_rate_n": metrics_mod.wasted_call_rate(results).n,
    }


_TABLE_METRICS_AGENT: list[tuple[str, str, str]] = [
    *_TABLE_METRICS,
    ("tool_calls_per_query", "tool_calls_per_query", "float"),
    ("wasted_call_rate", "wasted_call_rate", "pct"),
]


def build_report(
    model: str,
    timestamp: str,
    with_retrieval: list[QuestionMetricInputs],
    no_retrieval: list[QuestionMetricInputs],
) -> dict[str, Any]:
    splits_present = sorted({r.split for r in with_retrieval} | {r.split for r in no_retrieval})
    splits_data = {}
    for split in splits_present:
        splits_data[split] = {
            "with_retrieval": metrics_for([r for r in with_retrieval if r.split == split]),
            "no_retrieval": metrics_for([r for r in no_retrieval if r.split == split]),
        }

    return {"timestamp": timestamp, "model": model, "splits": splits_data}


def _fmt(value: Any, kind: str) -> str:
    if value is None:
        return "--"
    if kind == "pct":
        return f"{value * 100:.0f}%"
    if kind == "float":
        return f"{value:.2f}"
    if kind == "ms":
        return f"{value / 1000:.1f}s"
    if kind == "num":
        return f"{value:.0f}"
    if kind == "cost":
        return f"${value:.4f}"
    return str(value)


def build_comparison_report(
    model: str,
    timestamp: str,
    strategy_results: dict[str, list[QuestionMetricInputs]],
) -> dict[str, Any]:
    splits_present = sorted({r.split for results in strategy_results.values() for r in results})
    splits_data: dict[str, dict[str, Any]] = {}
    for split in splits_present:
        splits_data[split] = {
            strategy: metrics_for([r for r in results if r.split == split])
            for strategy, results in strategy_results.items()
        }

    return {"timestamp": timestamp, "model": model, "splits": splits_data}


def render_comparison_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SpecPilot Strategy Comparison",
        "",
        f"Model: {report['model']}    Generated: {report['timestamp']}",
        "",
    ]

    for split, strategies in report["splits"].items():
        n = next(iter(strategies.values()), {}).get("n", 0)
        lines.append(f"## {split} (n={n})")
        lines.append("")
        header_cells = " | ".join(label for _, label, _ in _TABLE_METRICS)
        lines.append(f"| strategy | {header_cells} |")
        lines.append("|---" * (len(_TABLE_METRICS) + 1) + "|")
        for strategy_name, metrics in strategies.items():
            cells = []
            for key, _, kind in _TABLE_METRICS:
                value = _fmt(metrics.get(key), kind)
                n_key = f"{key}_n"
                if n_key in metrics:
                    value = f"{value} (n={metrics[n_key]})"
                cells.append(value)
            lines.append(f"| {strategy_name} | " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SpecPilot Evaluation Report",
        "",
        f"Model: {report['model']}    Generated: {report['timestamp']}",
        "",
    ]

    for split, data in report["splits"].items():
        with_r, no_r = data["with_retrieval"], data["no_retrieval"]
        lines.append(f"## {split} (n={with_r.get('n', 0)})")
        lines.append("")
        lines.append("| metric | with retrieval | no retrieval |")
        lines.append("|---|---|---|")
        for key, label, kind in _TABLE_METRICS:
            n_key = f"{key}_n"
            with_val = _fmt(with_r.get(key), kind)
            no_val = _fmt(no_r.get(key), kind)
            if n_key in with_r:
                with_val = f"{with_val} (n={with_r[n_key]})"
            if n_key in no_r:
                no_val = f"{no_val} (n={no_r[n_key]})"
            lines.append(f"| {label} | {with_val} | {no_val} |")
        lines.append("")

    return "\n".join(lines)


def build_agent_report(
    model: str,
    timestamp: str,
    agent: list[QuestionMetricInputs],
    single_pass: list[QuestionMetricInputs],
) -> dict[str, Any]:
    splits_present = sorted({r.split for r in agent} | {r.split for r in single_pass})
    splits_data = {}
    for split in splits_present:
        splits_data[split] = {
            "agent": metrics_for([r for r in agent if r.split == split]),
            "single_pass": metrics_for([r for r in single_pass if r.split == split]),
        }

    return {"timestamp": timestamp, "model": model, "splits": splits_data}


def render_agent_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SpecPilot Agent vs Single-Pass Comparison",
        "",
        f"Model: {report['model']}    Generated: {report['timestamp']}",
        "",
        (
            "10 multi-step questions designed to need chained tool calls - a single "
            "retrieval pass should struggle with these."
        ),
        "",
    ]

    for split, data in report["splits"].items():
        agent_m, single_m = data["agent"], data["single_pass"]
        lines.append(f"## {split} (n={agent_m.get('n', 0)})")
        lines.append("")
        lines.append("| metric | agent | single-pass |")
        lines.append("|---|---|---|")
        for key, label, kind in _TABLE_METRICS_AGENT:
            n_key = f"{key}_n"
            agent_val = _fmt(agent_m.get(key), kind)
            single_val = _fmt(single_m.get(key), kind)
            if n_key in agent_m:
                agent_val = f"{agent_val} (n={agent_m[n_key]})"
            if n_key in single_m:
                single_val = f"{single_val} (n={single_m[n_key]})"
            lines.append(f"| {label} | {agent_val} | {single_val} |")
        lines.append("")

    return "\n".join(lines)
