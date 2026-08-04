from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.loop import AgentEvent, run_agent, stream_agent_events
from src.agent.tools import AgentContext
from src.answer.mistral_client import ChatClient
from src.answer.service import answer_question
from src.api.deps import get_agent_context, get_chat_client, get_retriever, get_session
from src.api.endpoints import router as endpoints_router
from src.api.providers import router as providers_router
from src.api.reports import router as reports_router
from src.api.schemas import AgentQueryResponse, QueryRequest, QueryResponse
from src.config import settings
from src.logging import configure_logging, get_logger
from src.observability import record_query, render_metrics
from src.retrieval.base import Retriever
from src.retrieval.factory import build_retriever

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="SpecPilot")
app.include_router(reports_router)
app.include_router(endpoints_router)
app.include_router(providers_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(render_metrics(), media_type="text/plain; version=0.0.4")


@app.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
    retriever: Retriever = Depends(get_retriever),
    chat_client: ChatClient = Depends(get_chat_client),
) -> QueryResponse:
    logger.info("query_received", question=request.question, top_k=request.top_k)
    start = time.perf_counter()
    answered = await answer_question(
        question=request.question,
        top_k=request.top_k,
        retriever=retriever,
        chat_client=chat_client,
        session=session,
        provider_id=request.provider_id,
    )
    record_query(
        "query",
        time.perf_counter() - start,
        answered.prompt_tokens,
        answered.completion_tokens,
    )
    return QueryResponse(**answered.result.model_dump())


@app.post("/agent/query", response_model=AgentQueryResponse)
async def agent_query(
    request: QueryRequest,
    context: AgentContext = Depends(get_agent_context),
    chat_client: ChatClient = Depends(get_chat_client),
) -> AgentQueryResponse:
    logger.info("agent_query_received", question=request.question, strategy=request.strategy)
    start = time.perf_counter()
    result = await run_agent(request.question, context, chat_client)
    record_query(
        "agent_query",
        time.perf_counter() - start,
        result.prompt_tokens,
        result.completion_tokens,
    )
    return AgentQueryResponse(
        answer=result.answer.answer,
        code_snippet=result.answer.code_snippet,
        citations=result.answer.citations,
        retrieved_chunk_ids=result.answer.retrieved_chunk_ids,
        trace=result.trace,
    )


def _format_sse(event: AgentEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _apply_screen_context(
    question: str, screen: str | None, context_method: str | None, context_path: str | None
) -> str:
    """BUILD.md Appendix B: the frontend sends the current screen with every turn so
    "what's required here?" works without naming the endpoint. SSE is a GET request with
    no body, so screen context travels as query params; this is where it's folded into
    the question the agent actually sees, since the agent loop itself only takes a
    plain-text question."""
    if not context_method or not context_path:
        return question
    return (
        f"(For context: the user is currently looking at the {screen or 'endpoint_detail'} "
        f"screen for {context_method} {context_path}. Resolve pronouns like "
        f'"here"/"this endpoint" against that unless the question clearly names a '
        f"different endpoint.)\n\n{question}"
    )


@app.get("/agent/stream/{session_id}")
async def agent_stream(
    session_id: str,
    question: str,
    strategy: str = settings.retrieval_strategy,
    top_k: int = settings.top_k_default,
    provider_id: str | None = None,
    screen: str | None = None,
    context_method: str | None = None,
    context_path: str | None = None,
    session: AsyncSession = Depends(get_session),
    chat_client: ChatClient = Depends(get_chat_client),
) -> StreamingResponse:
    """session_id is a client-generated correlation ID for this SSE connection, not a
    server-side session lookup - there is no separate "create session" step. The agent
    loop runs for the lifetime of this single GET request; disconnecting the client
    cancels the underlying generator, which is the "stop" behavior Phase 5's UI needs."""
    logger.info(
        "agent_stream_received",
        session_id=session_id,
        question=question,
        provider_id=provider_id,
        screen=screen,
        context_path=context_path,
    )
    effective_question = _apply_screen_context(question, screen, context_method, context_path)

    async def event_generator() -> AsyncIterator[str]:
        retriever = await build_retriever(strategy, session, provider_id)
        context = AgentContext(
            session=session, retriever=retriever, top_k_default=top_k, provider_id=provider_id
        )
        async for event in stream_agent_events(
            effective_question,
            context,
            chat_client,
            settings.agent_max_tool_calls,
            settings.agent_max_wall_clock_seconds,
            None,
        ):
            yield _format_sse(event)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# The built frontend (frontend/dist, produced by `npm run build`) is served from this
# same process in the Docker image, so one container is the whole deployable unit. In
# local dev the frontend runs on its own Vite server instead, so this only activates
# when the built assets are actually present - it must never affect `make dev` or tests.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets"
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """Registered last so it never shadows an API route above. Serves a matching
        static file (favicon.svg, icons.svg) if one exists, otherwise falls back to
        index.html so React Router can handle the client-side route itself."""
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
