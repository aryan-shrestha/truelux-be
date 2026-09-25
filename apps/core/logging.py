import logging
import re
from typing import Any

import structlog

REQUEST_ID_KEY = "request_id"

# Django's `log_response` writes the request path into the message, and an order's
# access_token is a path segment of /api/v1/orders/<access_token>/. ADR 0003 makes
# that token a bearer credential on convention.md's never-log list, so a single
# unhandled 500 on the order page would otherwise put it in Render's logs. Matching
# the shape rather than the one route keeps this true for any later path carrying
# one.
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
REDACTED = "<redacted>"


def _redact(value: Any) -> Any:
    return UUID_PATTERN.sub(REDACTED, value) if isinstance(value, str) else value


class RedactUUIDs(logging.Filter):
    """Removes UUIDs from a record's message before any handler formats it.

    Attached to `django.request` only. The application's own lines log identifiers
    deliberately -- `order.placed` carries `order_id` -- and go through `apps`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: _redact(value) for key, value in record.args.items()}
        elif record.args:
            record.args = tuple(_redact(arg) for arg in record.args)
        return True


def _ensure_request_id(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    # Lines emitted outside a request -- boot, management commands -- still carry the
    # key, so a log query filtering on request_id never silently drops them.
    event_dict.setdefault(REQUEST_ID_KEY, "")
    return event_dict


SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    _ensure_request_id,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


class JSONFormatter(structlog.stdlib.ProcessorFormatter):
    """Renders structlog events and plain stdlib records as one JSON line each."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("foreign_pre_chain", SHARED_PROCESSORS)
        kwargs.setdefault(
            "processors",
            [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
        super().__init__(*args, **kwargs)


def configure_structlog() -> None:
    structlog.configure(
        processors=[
            *SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Bind the request id from RequestIDMiddleware into every line this logger emits."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
