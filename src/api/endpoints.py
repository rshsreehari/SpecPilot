from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.models import Endpoint, Parameter

router = APIRouter(prefix="/api/endpoints", tags=["endpoints"])


@router.get("")
async def list_endpoints(
    q: str | None = None,
    provider_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    stmt = select(Endpoint).order_by(Endpoint.path, Endpoint.method)
    if provider_id:
        stmt = stmt.where(Endpoint.provider_id == provider_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Endpoint.path.ilike(pattern),
                Endpoint.summary.ilike(pattern),
                Endpoint.operation_id.ilike(pattern),
            )
        )
    endpoints = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": e.id,
            "provider_id": e.provider_id,
            "method": e.method,
            "path": e.path,
            "operation_id": e.operation_id,
            "summary": e.summary,
        }
        for e in endpoints
    ]


@router.get("/{endpoint_id}")
async def get_endpoint_detail(
    endpoint_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    endpoint = await session.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"endpoint {endpoint_id} not found")

    params = (
        (await session.execute(select(Parameter).where(Parameter.endpoint_id == endpoint_id)))
        .scalars()
        .all()
    )
    return {
        "id": endpoint.id,
        "provider_id": endpoint.provider_id,
        "method": endpoint.method,
        "path": endpoint.path,
        "operation_id": endpoint.operation_id,
        "summary": endpoint.summary,
        "description": endpoint.description,
        "parameters": [
            {
                "name": p.name,
                "location": p.location,
                "type": p.type,
                "required": p.required,
                "description": p.description,
            }
            for p in params
        ],
    }
