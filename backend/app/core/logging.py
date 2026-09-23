"""Structured logging.

Logs are for operators debugging the system. The *run timeline* is the agent's own record
and lives in the event bus — these are different things and deliberately do not share a
pipeline. A log line is allowed to be noisy and transient; an execution event is not.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings

_configured = False


def configure_logging(level: str | None = None) -> None:
    """Idempotent. Safe to call from tests, the CLI and the API startup path alike."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    log_level = (level or settings.log_level).upper()

    # ASCII-only renderer output: the Windows console is cp1252 by default (BUG-001).
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str, **initial: Any) -> structlog.stdlib.BoundLogger:
    configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name).bind(**initial)
    return logger
