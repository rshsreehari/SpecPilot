from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

REPORTS_DIR = Path("eval/reports")

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _report_kind(path: Path) -> str:
    if path.name.startswith("comparison-"):
        return "comparison"
    if path.name.startswith("agent-"):
        return "agent"
    return "eval"


def _report_id(path: Path) -> str:
    return path.stem


def _report_providers(report: dict[str, Any]) -> list[str]:
    if "providers" in report:
        return list(report["providers"])
    if "provider" in report:
        return [report["provider"]]
    return []


@router.get("")
async def list_reports(provider_id: str | None = None) -> list[dict[str, Any]]:
    """Newest first. Each entry is enough to populate a report picker without fetching
    every report body - the UI fetches the full JSON via GET /api/reports/{id} on demand.
    provider_id filters to reports for one provider, matching either a single-provider
    report's "provider" field or an all-providers report's "providers" list."""
    if not REPORTS_DIR.is_dir():
        return []

    paths = sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    summaries = []
    for path in paths:
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        providers = _report_providers(report)
        if provider_id and provider_id not in providers:
            continue
        summaries.append(
            {
                "id": _report_id(path),
                "kind": _report_kind(path),
                "model": report.get("model"),
                "timestamp": report.get("timestamp"),
                "providers": providers,
                "splits": list(report.get("splits", {}).keys()),
            }
        )
    return summaries


@router.get("/{report_id}")
async def get_report(report_id: str) -> dict[str, Any]:
    path = REPORTS_DIR / f"{report_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"report {report_id!r} not found")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=500, detail="report file is not valid JSON") from error
