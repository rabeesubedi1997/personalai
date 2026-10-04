"""
Structured logging setup.

Uses structlog so every log line is a JSON object with consistent fields —
this is what lets later phases answer "what did the agent do, with which
tool, with what result" (spec Section 25, Audit Logging) by grepping/querying
logs, not by re-reading prose.

Never log secrets (API keys, passwords, tokens) — see app.core.config for
where those live; they must never be passed into a log call.
"""
import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
