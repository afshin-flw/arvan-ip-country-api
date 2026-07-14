import logging
import sys
from typing import Any

import structlog

from ip_country_api.observability.request_context import request_id_context

SENSITIVE_KEYS = frozenset(
    {"authorization", "cookie", "database_url", "ipinfo_token", "password", "secret", "token"}
)


def redact_secrets(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def add_request_id(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("request_id", request_id_context.get())
    return event_dict


def configure_logging(level: str, output_format: str) -> None:
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if output_format == "console"
        else structlog.processors.JSONRenderer()
    )
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        renderer,
    ]
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
