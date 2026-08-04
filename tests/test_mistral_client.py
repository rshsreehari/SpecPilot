from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from mistralai.client.errors import SDKError

from src.answer.mistral_client import MistralChatClient


def _response(content: str, tool_calls: list[Any] | None = None) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _rate_limit_error(retry_after: str | None = None) -> SDKError:
    headers = {"retry-after": retry_after} if retry_after else {}
    raw = httpx.Response(status_code=429, headers=headers, request=httpx.Request("POST", "https://x"))
    return SDKError("rate limited", raw)


def _server_error() -> SDKError:
    raw = httpx.Response(status_code=500, request=httpx.Request("POST", "https://x"))
    return SDKError("server error", raw)


@pytest.fixture
def client() -> MistralChatClient:
    # Never makes a real network call in these tests - complete_async is monkeypatched
    # per-test at the client boundary, per CLAUDE.md ("never call a live model").
    return MistralChatClient()


async def test_chat_json_parses_valid_json(client: MistralChatClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        return _response('{"answer": "hi", "code_snippet": null, "citations": []}')

    monkeypatch.setattr(client._client.chat, "complete_async", fake_complete)

    result = await client.chat_json("system", "user")

    assert result.data == {"answer": "hi", "code_snippet": None, "citations": []}
    assert result.prompt_tokens == 10


async def test_chat_json_falls_back_on_invalid_json(
    client: MistralChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        return _response("not json")

    monkeypatch.setattr(client._client.chat, "complete_async", fake_complete)

    result = await client.chat_json("system", "user")

    assert result.data == {"answer": "not json", "code_snippet": None, "citations": []}


async def test_chat_raw_parses_tool_call_arguments_from_json_string(
    client: MistralChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_call = SimpleNamespace(
        id="call_1", function=SimpleNamespace(name="search_docs", arguments='{"query": "x"}')
    )

    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        return _response("", tool_calls=[tool_call])

    monkeypatch.setattr(client._client.chat, "complete_async", fake_complete)

    raw = await client.chat_raw(messages=[])

    assert raw.tool_calls[0].name == "search_docs"
    assert raw.tool_calls[0].arguments == {"query": "x"}


async def test_chat_raw_handles_malformed_tool_call_arguments(
    client: MistralChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_call = SimpleNamespace(
        id="call_1", function=SimpleNamespace(name="search_docs", arguments="not json")
    )

    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        return _response("", tool_calls=[tool_call])

    monkeypatch.setattr(client._client.chat, "complete_async", fake_complete)

    raw = await client.chat_raw(messages=[])

    assert raw.tool_calls[0].arguments == {}


async def test_retries_on_429_then_succeeds(
    client: MistralChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.answer.mistral_client.asyncio.sleep", _noop_sleep)
    attempts = {"count": 0}

    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _rate_limit_error(retry_after="0")
        return _response("ok")

    monkeypatch.setattr(client._client.chat, "complete_async", fake_complete)

    raw = await client.chat_raw(messages=[])

    assert raw.content == "ok"
    assert attempts["count"] == 3


async def test_non_429_error_is_not_retried(
    client: MistralChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_complete(**kwargs: Any) -> SimpleNamespace:
        raise _server_error()

    monkeypatch.setattr(client._client.chat, "complete_async", fake_complete)

    with pytest.raises(SDKError):
        await client.chat_raw(messages=[])


async def _noop_sleep(_seconds: float) -> None:
    return None
