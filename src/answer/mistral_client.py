from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol

from mistralai.client import Mistral
from mistralai.client.errors import SDKError

from src.config import settings
from src.logging import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 5
_BASE_DELAY_SECONDS = 2.0


@dataclass
class ChatResponse:
    data: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int


@dataclass
class RawToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class RawChatMessage:
    content: str
    tool_calls: list[RawToolCall]
    prompt_tokens: int
    completion_tokens: int


class ChatClient(Protocol):
    async def chat_json(
        self, system: str, user: str, seed: int | None = None
    ) -> ChatResponse: ...

    async def chat_raw(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> RawChatMessage: ...


class MistralChatClient:
    def __init__(self) -> None:
        self._client = Mistral(api_key=settings.mistral_api_key)

    async def chat_json(self, system: str, user: str, seed: int | None = None) -> ChatResponse:
        raw = await self.chat_raw(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            seed=seed,
        )
        try:
            data: dict[str, Any] = json.loads(raw.content)
        except json.JSONDecodeError:
            logger.warning("mistral_json_parse_failed", content=raw.content)
            data = {"answer": raw.content, "code_snippet": None, "citations": []}

        return ChatResponse(
            data=data, prompt_tokens=raw.prompt_tokens, completion_tokens=raw.completion_tokens
        )

    async def chat_raw(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> RawChatMessage:
        response = await self._complete_with_retry(
            messages, tools, tool_choice, response_format, seed
        )
        message = response.choices[0].message
        usage = response.usage

        tool_calls: list[RawToolCall] = []
        for call in message.tool_calls or []:
            arguments = call.function.arguments
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    logger.warning("mistral_tool_args_parse_failed", arguments=arguments)
                    arguments = {}
            tool_calls.append(
                RawToolCall(id=call.id or "", name=call.function.name, arguments=arguments)
            )

        return RawChatMessage(
            content=message.content or "",
            tool_calls=tool_calls,
            prompt_tokens=usage.prompt_tokens or 0,
            completion_tokens=usage.completion_tokens or 0,
        )

    async def _complete_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        response_format: dict[str, Any] | None,
        seed: int | None,
    ) -> Any:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self._client.chat.complete_async(
                    model=settings.mistral_model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    response_format=response_format,
                    random_seed=seed,
                    max_tokens=settings.mistral_max_tokens,
                )
            except SDKError as error:
                if error.status_code != 429 or attempt == _MAX_RETRIES:
                    raise
                retry_after = error.headers.get("retry-after")
                delay = float(retry_after) if retry_after else _BASE_DELAY_SECONDS * 2**attempt
                logger.warning("mistral_rate_limited", attempt=attempt, delay_seconds=delay)
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")
