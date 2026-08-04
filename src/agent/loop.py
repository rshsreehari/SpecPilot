from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel

from src.agent.tools import TOOL_DEFINITIONS, AgentContext, ToolExecution, execute_tool
from src.answer.mistral_client import ChatClient
from src.answer.schemas import AnswerResult, Citation
from src.config import settings
from src.eval.truth import verify_endpoint
from src.logging import get_logger
from src.observability import record_tool_call

ToolExecutor = Callable[[str, dict[str, Any], AgentContext], Awaitable[ToolExecution]]

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are SpecPilot's agent, answering questions about an API using tools \
to look up documentation. You have four tools:
  search_docs(query, top_k)        - search documentation for relevant passages
  get_endpoint(method, path)       - full detail for one specific endpoint
  list_parameters(method, path)    - parameters for one specific endpoint
  find_related(operation_id)       - other endpoints in the same resource family

Some questions need several tool calls chained together. Prefer starting with search_docs
to find the right endpoint(s), then follow up: use get_endpoint or list_parameters to
confirm exact parameter names before stating them as fact, and use find_related whenever
the question involves a related action, an alternative endpoint, or what else exists in
the same resource family. Do not answer from search_docs alone if the question asks about
required fields, related endpoints, or a multi-step process - verify with a follow-up tool
call first. Use as many tool calls as you genuinely need, one at a time, but do not call a
tool you already have the answer from.

Answer only from what your tools return. If you still don't have enough information after
using your tools, say so explicitly rather than guessing.
"""

FINAL_ANSWER_INSTRUCTION = """Based on everything above, respond with a single flat JSON \
object with exactly these keys - do not nest another JSON object or code block inside any
of these values, and do not wrap the whole thing in markdown fences:
  "answer": plain text string, a concise natural-language answer. Not JSON, not markdown.
  "code_snippet": string or null, an example code snippet if relevant.
  "citations": array of objects with "method", "path", "operation_id" (operation_id may be \
null), one per endpoint you relied on.
"""

BUDGET_EXHAUSTED_NOTE = (
    "You have used all available tool calls or run out of time. Answer now with what you "
    "have gathered, and explicitly state what you could not determine.\n\n"
)


class ToolStartEvent(BaseModel):
    type: Literal["tool_start"] = "tool_start"
    step: int
    tool: str
    args: dict[str, Any]


class ToolEndEvent(BaseModel):
    type: Literal["tool_end"] = "tool_end"
    step: int
    tool: str
    duration_ms: float
    summary: str


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    answer: AnswerResult
    trace: list[TraceStep]
    prompt_tokens: int
    completion_tokens: int


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


AgentEvent = ToolStartEvent | ToolEndEvent | TokenEvent | DoneEvent | ErrorEvent


class TraceStep(BaseModel):
    step: int
    tool: str
    args: dict[str, Any]
    result_summary: str
    duration_ms: float
    endpoint_ids: list[int]


class AgentResult(BaseModel):
    answer: AnswerResult
    trace: list[TraceStep]
    prompt_tokens: int
    completion_tokens: int


DoneEvent.model_rebuild()


def _summarize(tool: str, result: dict[str, Any]) -> str:
    if "error" in result:
        return str(result["error"])
    if tool == "search_docs":
        return f"{len(result.get('results', []))} results"
    if tool == "get_endpoint":
        return f"{result.get('method')} {result.get('path')}: {len(result.get('parameters', []))} parameters"
    if tool == "list_parameters":
        return f"{len(result.get('parameters', []))} parameters"
    if tool == "find_related":
        return f"{len(result.get('endpoints', []))} related endpoints"
    return "done"


async def stream_agent_events(
    question: str,
    context: AgentContext,
    chat_client: ChatClient,
    max_tool_calls: int,
    max_wall_clock_seconds: float,
    seed: int | None,
    tool_executor: ToolExecutor = execute_tool,
) -> AsyncIterator[AgentEvent]:
    start = time.perf_counter()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    trace: list[TraceStep] = []
    tool_call_count = 0
    budget_exhausted = False
    prompt_tokens = 0
    completion_tokens = 0

    try:
        while True:
            elapsed = time.perf_counter() - start
            if tool_call_count >= max_tool_calls or elapsed >= max_wall_clock_seconds:
                budget_exhausted = True
                break

            raw = await chat_client.chat_raw(
                messages=messages, tools=TOOL_DEFINITIONS, tool_choice="auto", seed=seed
            )
            prompt_tokens += raw.prompt_tokens
            completion_tokens += raw.completion_tokens
            if not raw.tool_calls:
                break

            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments},
                        }
                        for call in raw.tool_calls
                    ],
                }
            )

            for call in raw.tool_calls:
                if tool_call_count >= max_tool_calls:
                    budget_exhausted = True
                    break

                tool_call_count += 1
                step = tool_call_count
                yield ToolStartEvent(step=step, tool=call.name, args=call.arguments)

                call_start = time.perf_counter()
                execution = await tool_executor(call.name, call.arguments, context)
                duration_ms = (time.perf_counter() - call_start) * 1000
                summary = _summarize(call.name, execution.result)
                record_tool_call(call.name)

                trace.append(
                    TraceStep(
                        step=step,
                        tool=call.name,
                        args=call.arguments,
                        result_summary=summary,
                        duration_ms=round(duration_ms, 1),
                        endpoint_ids=execution.endpoint_ids,
                    )
                )
                yield ToolEndEvent(step=step, tool=call.name, duration_ms=duration_ms, summary=summary)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": _json_dumps(execution.result),
                    }
                )

            if time.perf_counter() - start >= max_wall_clock_seconds:
                budget_exhausted = True
                break

        closing = FINAL_ANSWER_INSTRUCTION
        if budget_exhausted:
            closing = BUDGET_EXHAUSTED_NOTE + closing
        messages.append({"role": "user", "content": closing})

        final = await chat_client.chat_raw(
            messages=messages, response_format={"type": "json_object"}, seed=seed
        )
        prompt_tokens += final.prompt_tokens
        completion_tokens += final.completion_tokens
        result = _parse_final_answer(final.content, context.provider_id)
        yield TokenEvent(text=result.answer)
        yield DoneEvent(
            answer=result,
            trace=trace,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception as error:  # noqa: BLE001 - surfaced to the caller as an SSE error event
        logger.warning("agent_loop_error", error=str(error))
        yield ErrorEvent(message=str(error))


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data)


def _parse_final_answer(content: str, provider_id: str | None) -> AnswerResult:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("agent_final_answer_parse_failed", content=content)
        return AnswerResult(answer=content, code_snippet=None, citations=[], retrieved_chunk_ids=[])

    # Occasionally the model double-wraps its answer: the outer "answer" field is
    # itself a JSON-encoded string containing the real {answer, code_snippet, citations}
    # object, instead of populating the top-level fields directly (more likely after a
    # long tool-heavy conversation). Unwrap one level if that's what happened.
    inner = data.get("answer")
    if isinstance(inner, str) and inner.strip().startswith("{"):
        try:
            inner_data = json.loads(inner.strip())
        except json.JSONDecodeError:
            inner_data = None
        if isinstance(inner_data, dict) and "answer" in inner_data:
            data = inner_data

    citations: list[Citation] = []
    for raw_citation in data.get("citations", []):
        try:
            citation = Citation(**raw_citation)
        except (TypeError, ValueError):
            logger.warning("agent_citation_parse_failed", raw_citation=raw_citation)
            continue
        resolved_provider = citation.provider_id or provider_id
        citations.append(
            citation.model_copy(
                update={
                    "provider_id": resolved_provider,
                    "verified": verify_endpoint(resolved_provider, citation.method, citation.path),
                }
            )
        )

    return AnswerResult(
        answer=data.get("answer", ""),
        code_snippet=data.get("code_snippet"),
        citations=citations,
        retrieved_chunk_ids=[],
    )


async def run_agent(
    question: str,
    context: AgentContext,
    chat_client: ChatClient,
    max_tool_calls: int | None = None,
    max_wall_clock_seconds: float | None = None,
    seed: int | None = None,
    tool_executor: ToolExecutor = execute_tool,
) -> AgentResult:
    resolved_max_calls = max_tool_calls if max_tool_calls is not None else settings.agent_max_tool_calls
    resolved_max_seconds = (
        max_wall_clock_seconds
        if max_wall_clock_seconds is not None
        else settings.agent_max_wall_clock_seconds
    )

    async for event in stream_agent_events(
        question,
        context,
        chat_client,
        resolved_max_calls,
        resolved_max_seconds,
        seed,
        tool_executor,
    ):
        if isinstance(event, DoneEvent):
            return AgentResult(
                answer=event.answer,
                trace=event.trace,
                prompt_tokens=event.prompt_tokens,
                completion_tokens=event.completion_tokens,
            )
        if isinstance(event, ErrorEvent):
            return AgentResult(
                answer=AnswerResult(
                    answer=f"Agent error: {event.message}",
                    code_snippet=None,
                    citations=[],
                    retrieved_chunk_ids=[],
                ),
                trace=[],
                prompt_tokens=0,
                completion_tokens=0,
            )

    raise AssertionError("agent event stream ended without a done or error event")
