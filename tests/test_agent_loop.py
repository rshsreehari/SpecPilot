from __future__ import annotations

import json
from typing import Any

from src.agent.loop import BUDGET_EXHAUSTED_NOTE, run_agent
from src.agent.tools import AgentContext, ToolExecution
from src.answer.mistral_client import RawChatMessage, RawToolCall


class ScriptedChatClient:
    """Mocked at the ChatClient boundary, per CLAUDE.md - never calls a live model."""

    def __init__(self, responses: list[RawChatMessage]) -> None:
        self._responses = responses
        self.call_count = 0
        self.received_messages: list[list[dict[str, Any]]] = []

    async def chat_raw(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> RawChatMessage:
        self.received_messages.append(messages)
        response = self._responses[self.call_count]
        self.call_count += 1
        return response

    async def chat_json(self, system: str, user: str, seed: int | None = None) -> Any:
        raise NotImplementedError("agent loop tests only use chat_raw")


def _final_answer_message(answer: str, citations: list[dict[str, Any]] | None = None) -> RawChatMessage:
    content = json.dumps({"answer": answer, "code_snippet": None, "citations": citations or []})
    return RawChatMessage(content=content, tool_calls=[], prompt_tokens=10, completion_tokens=10)


def _tool_call_message(tool: str, args: dict[str, Any], call_id: str = "call_1") -> RawChatMessage:
    return RawChatMessage(
        content="",
        tool_calls=[RawToolCall(id=call_id, name=tool, arguments=args)],
        prompt_tokens=10,
        completion_tokens=5,
    )


def _no_more_tools_message() -> RawChatMessage:
    """After a tool-call round, the loop always asks again whether more tools are
    needed. This response is that check answering "no" - the loop then always makes a
    separate, dedicated final-synthesis call after it (with response_format=json_object
    and no tools), so a tool-call round costs 2 chat_raw calls: the round itself plus
    this check, not counting the closing synthesis call."""
    return RawChatMessage(content="", tool_calls=[], prompt_tokens=5, completion_tokens=5)


async def _fake_tool_executor(name: str, args: dict[str, Any], context: AgentContext) -> ToolExecution:
    return ToolExecution(result={"echo": name, "args": args}, endpoint_ids=[1, 2])


def _context() -> AgentContext:
    return AgentContext(session=None, retriever=None, top_k_default=5)  # type: ignore[arg-type]


async def test_natural_stop_produces_answer_with_no_tool_calls() -> None:
    chat_client = ScriptedChatClient(
        [
            RawChatMessage(content="", tool_calls=[], prompt_tokens=5, completion_tokens=5),
            _final_answer_message("no tools were needed"),
        ]
    )

    result = await run_agent(
        "trivial question", _context(), chat_client, tool_executor=_fake_tool_executor
    )

    assert result.answer.answer == "no tools were needed"
    assert result.trace == []
    assert chat_client.call_count == 2


async def test_single_tool_call_is_recorded_in_trace() -> None:
    chat_client = ScriptedChatClient(
        [
            _tool_call_message("search_docs", {"query": "cancel subscription"}),
            _no_more_tools_message(),
            _final_answer_message("use POST /v1/subscriptions/{id}"),
        ]
    )

    result = await run_agent(
        "how do I cancel?", _context(), chat_client, tool_executor=_fake_tool_executor
    )

    assert len(result.trace) == 1
    step = result.trace[0]
    assert step.step == 1
    assert step.tool == "search_docs"
    assert step.args == {"query": "cancel subscription"}
    assert step.endpoint_ids == [1, 2]
    assert step.duration_ms >= 0


async def test_multi_step_trace_records_steps_in_order() -> None:
    chat_client = ScriptedChatClient(
        [
            _tool_call_message("search_docs", {"query": "resume subscription"}, call_id="c1"),
            _tool_call_message("get_endpoint", {"method": "POST", "path": "/v1/x"}, call_id="c2"),
            _no_more_tools_message(),
            _final_answer_message("resume via POST /v1/x"),
        ]
    )

    result = await run_agent(
        "multi-step question", _context(), chat_client, tool_executor=_fake_tool_executor
    )

    assert [step.tool for step in result.trace] == ["search_docs", "get_endpoint"]
    assert [step.step for step in result.trace] == [1, 2]


async def test_budget_enforcement_never_exceeds_max_tool_calls() -> None:
    # A client that always wants to call another tool - the loop must stop at the cap
    # regardless, never running the tool a 3rd time.
    chat_client = ScriptedChatClient(
        [
            _tool_call_message("search_docs", {"query": "a"}, call_id="c1"),
            _tool_call_message("search_docs", {"query": "b"}, call_id="c2"),
            _final_answer_message("answered within budget"),
        ]
    )

    result = await run_agent(
        "question",
        _context(),
        chat_client,
        max_tool_calls=2,
        tool_executor=_fake_tool_executor,
    )

    assert len(result.trace) == 2
    assert chat_client.call_count == 3  # 2 tool-requesting calls + 1 final synthesis
    # The final synthesis call must have been told the budget ran out.
    final_messages = chat_client.received_messages[-1]
    assert any(BUDGET_EXHAUSTED_NOTE in m.get("content", "") for m in final_messages)


async def test_wall_clock_budget_of_zero_skips_all_tool_calls() -> None:
    chat_client = ScriptedChatClient([_final_answer_message("no time for tools")])

    result = await run_agent(
        "question",
        _context(),
        chat_client,
        max_wall_clock_seconds=0.0,
        tool_executor=_fake_tool_executor,
    )

    assert result.trace == []
    assert chat_client.call_count == 1
    final_messages = chat_client.received_messages[-1]
    assert any(BUDGET_EXHAUSTED_NOTE in m.get("content", "") for m in final_messages)


async def test_tool_error_result_does_not_crash_the_loop() -> None:
    async def failing_tool_executor(
        name: str, args: dict[str, Any], context: AgentContext
    ) -> ToolExecution:
        return ToolExecution(result={"error": "no endpoint found"}, endpoint_ids=[])

    chat_client = ScriptedChatClient(
        [
            _tool_call_message("get_endpoint", {"method": "GET", "path": "/v1/nonexistent"}),
            _no_more_tools_message(),
            _final_answer_message("could not find that endpoint"),
        ]
    )

    result = await run_agent(
        "question", _context(), chat_client, tool_executor=failing_tool_executor
    )

    assert result.trace[0].result_summary == "no endpoint found"
    assert result.answer.answer == "could not find that endpoint"


async def test_chat_client_exception_produces_graceful_error_result() -> None:
    class RaisingChatClient:
        async def chat_raw(self, *args: Any, **kwargs: Any) -> RawChatMessage:
            raise RuntimeError("network exploded")

        async def chat_json(self, *args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError

    result = await run_agent(
        "question", _context(), RaisingChatClient(), tool_executor=_fake_tool_executor
    )

    assert "network exploded" in result.answer.answer
    assert result.trace == []


async def test_malformed_final_json_falls_back_to_raw_content_as_answer() -> None:
    chat_client = ScriptedChatClient(
        [
            _no_more_tools_message(),
            RawChatMessage(
                content="not json at all", tool_calls=[], prompt_tokens=5, completion_tokens=5
            ),
        ]
    )

    result = await run_agent(
        "question", _context(), chat_client, tool_executor=_fake_tool_executor
    )

    assert result.answer.answer == "not json at all"
    assert result.answer.citations == []


async def test_double_nested_final_json_is_unwrapped() -> None:
    # Observed live: after a long tool-heavy conversation, the model sometimes wraps the
    # real {answer, code_snippet, citations} object as a JSON string inside the outer
    # "answer" field instead of populating top-level keys directly.
    inner = json.dumps(
        {
            "answer": "use POST /v1/subscriptions/{id}",
            "code_snippet": "stripe.Subscription.modify(...)",
            "citations": [
                {"method": "POST", "path": "/v1/subscriptions/{id}", "operation_id": "X"}
            ],
        }
    )
    outer = json.dumps({"answer": inner, "code_snippet": None, "citations": []})
    chat_client = ScriptedChatClient(
        [
            _no_more_tools_message(),
            RawChatMessage(content=outer, tool_calls=[], prompt_tokens=5, completion_tokens=5),
        ]
    )

    result = await run_agent(
        "question", _context(), chat_client, tool_executor=_fake_tool_executor
    )

    assert result.answer.answer == "use POST /v1/subscriptions/{id}"
    assert result.answer.code_snippet == "stripe.Subscription.modify(...)"
    assert len(result.answer.citations) == 1
    assert result.answer.citations[0].path == "/v1/subscriptions/{id}"


async def test_malformed_citation_entries_are_skipped_not_fatal() -> None:
    content = json.dumps(
        {
            "answer": "some answer",
            "code_snippet": None,
            "citations": [{"not_a_valid_citation_shape": True}],
        }
    )
    chat_client = ScriptedChatClient(
        [
            _no_more_tools_message(),
            RawChatMessage(content=content, tool_calls=[], prompt_tokens=5, completion_tokens=5),
        ]
    )

    result = await run_agent(
        "question", _context(), chat_client, tool_executor=_fake_tool_executor
    )

    assert result.answer.answer == "some answer"
    assert result.answer.citations == []
