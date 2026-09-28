from typing import Any

from django.core.exceptions import ObjectDoesNotExist, SuspiciousOperation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.logging import get_logger

logger = get_logger(__name__)

# The published code for every exception this API raises, stated here rather than
# read from `exc.default_code`. `default_code` belongs to DRF: a DRF upgrade that
# renames one would silently change this API's public contract, and nothing would
# fail until a client broke in production. Two already disagree with the error
# table in docs/architecture.md -- DRF spells them "invalid" and
# "not_authenticated" -- and the documented spelling wins.
#
# Order matters: the first match wins, so subclasses precede their base.
_PUBLISHED_CODES: tuple[tuple[type[APIException], str], ...] = (
    (ValidationError, "validation_error"),
    (NotAuthenticated, "authentication_failed"),
    (AuthenticationFailed, "authentication_failed"),
    (PermissionDenied, "permission_denied"),
    (NotFound, "not_found"),
    (Throttled, "throttled"),
    (MethodNotAllowed, "method_not_allowed"),
    (UnsupportedMediaType, "unsupported_media_type"),
    (NotAcceptable, "not_acceptable"),
    (ParseError, "parse_error"),
)

# An exception with no published code reports this rather than leaking whatever DRF
# happens to call it internally.
FALLBACK_CODE = "error"
FALLBACK_MESSAGE = "The request could not be completed."


class DomainError(Exception):
    """Base for business-rule failures. Subclasses set `code` and `message`."""

    code = "domain_error"
    message = FALLBACK_MESSAGE
    status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, *, message: str | None = None, details: dict[str, Any] | None = None):
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


def _envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _first_message(data: Any) -> str:
    if isinstance(data, dict):
        for value in data.values():
            return _first_message(value)
        return FALLBACK_MESSAGE
    if isinstance(data, list):
        return _first_message(data[0]) if data else FALLBACK_MESSAGE
    return str(data)


def _describe(data: Any) -> tuple[str, dict[str, Any]]:
    """Split a DRF response body into a human message and machine-readable details."""
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is not None and len(data) == 1:
            return str(detail), {}
        return _first_message(data), data
    return _first_message(data), {}


def _code_for(exc: Exception) -> str:
    for exc_type, code in _PUBLISHED_CODES:
        if isinstance(exc, exc_type):
            return code
    if isinstance(exc, APIException):
        return FALLBACK_CODE
    return "server_error"


def _constraint_name(exc: IntegrityError) -> str | None:
    # psycopg exposes the violated constraint on the wrapped driver error. The name
    # is schema metadata, unlike the exception message, which embeds the row values.
    diagnostics = getattr(exc.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        return Response(_envelope(exc.code, exc.message, exc.details), status=exc.status_code)

    if isinstance(exc, IntegrityError):
        logger.warning("db.integrity_error", constraint=_constraint_name(exc))
        return Response(
            _envelope("conflict", "The write conflicted with an existing record."),
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        exc = ValidationError(detail=detail)

    # Selectors scope their querysets to what the caller may see and let the miss
    # propagate, per convention.md, so "no such row" and "row you may not see"
    # arrive here as the same exception and leave as the same 404.
    if isinstance(exc, ObjectDoesNotExist):
        exc = NotFound()

    # Django raises these while parsing a malformed or oversized body, such as
    # TooManyFieldsSent and RequestDataTooBig. They are the client's fault, and
    # Django itself answers them with a 400.
    if isinstance(exc, SuspiciousOperation):
        logger.warning("request.suspicious_operation", error=type(exc).__name__)
        exc = ParseError()

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.exception("request.unhandled_exception")
        return Response(
            _envelope("server_error", "An unexpected error occurred."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    message, details = _describe(response.data)
    response.data = _envelope(_code_for(exc), message, details)
    return response
