from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from src.agent import tools as agent_tools
from src.agent.tools import AgentContext
from src.config import settings
from src.db import async_session_maker
from src.retrieval.factory import build_retriever

server = MCPServer(
    name="specpilot",
    version="0.1.0",
    description=(
        "Search and inspect any OpenAPI 3.x provider ingested into SpecPilot."
    ),
)


@server.tool(
    description="Search the API documentation for passages relevant to a query, using "
    "the currently configured retrieval strategy."
)
async def search_docs(query: str, top_k: int = 5) -> dict[str, Any]:
    async with async_session_maker() as session:
        retriever = await build_retriever(settings.retrieval_strategy, session)
        context = AgentContext(session=session, retriever=retriever)
        execution = await agent_tools.search_docs(query, top_k, context)
        return execution.result


@server.tool(
    description="Get full detail - summary, description, and parameters - for one "
    "specific endpoint identified by HTTP method and path."
)
async def get_endpoint(method: str, path: str) -> dict[str, Any]:
    async with async_session_maker() as session:
        retriever = await build_retriever(settings.retrieval_strategy, session)
        context = AgentContext(session=session, retriever=retriever)
        execution = await agent_tools.get_endpoint(method, path, context)
        return execution.result


@server.tool(
    description="List the parameters - name, location, type, required flag - for one "
    "specific endpoint identified by HTTP method and path."
)
async def list_parameters(method: str, path: str) -> dict[str, Any]:
    async with async_session_maker() as session:
        retriever = await build_retriever(settings.retrieval_strategy, session)
        context = AgentContext(session=session, retriever=retriever)
        execution = await agent_tools.list_parameters(method, path, context)
        return execution.result


@server.tool(
    description="Find other endpoints related to a given one (same resource family), "
    "identified by its operation_id."
)
async def find_related(operation_id: str) -> dict[str, Any]:
    async with async_session_maker() as session:
        retriever = await build_retriever(settings.retrieval_strategy, session)
        context = AgentContext(session=session, retriever=retriever)
        execution = await agent_tools.find_related(operation_id, context)
        return execution.result


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
