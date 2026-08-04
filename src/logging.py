from __future__ import annotations

import logging
import sys
from collections import Counter
from typing import Any

import structlog

# Counts every warning-level log event by its event name (e.g. "ref_cycle",
# "ref_missing") for the lifetime of the process. Ingestion uses this to print a
# per-provider "skipped items, with reasons" summary without threading a diagnostics
# object through every parser function - a pure side-channel, never read by anything
# that affects parsing behavior itself.
warning_counts: Counter[str] = Counter()


def _count_warnings(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    if method_name == "warning":
        warning_counts[event_dict.get("event", "unknown")] += 1
    return event_dict


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            _count_warnings,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
