import json
import logging

import pytest
import structlog

from apps.core.logging import JSONFormatter, RedactUUIDs, configure_structlog, get_logger


@pytest.fixture(autouse=True)
def _structlog_configured():
    configure_structlog()
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


@pytest.fixture
def captured(caplog):
    caplog.set_level(logging.INFO)
    formatter = JSONFormatter()

    def _render():
        return [json.loads(formatter.format(record)) for record in caplog.records]

    return _render


def test_event_name_and_level_are_rendered(captured):
    get_logger("apps.test").info("order.created")

    payload = captured()[0]

    assert payload["event"] == "order.created"
    assert payload["level"] == "info"
    assert payload["logger"] == "apps.test"


def test_keyword_context_becomes_top_level_keys(captured):
    get_logger("apps.test").info("order.created", order_id="abc", item_count=2)

    payload = captured()[0]

    assert payload["order_id"] == "abc"
    assert payload["item_count"] == 2


def test_bound_request_id_appears_on_the_line(captured):
    structlog.contextvars.bind_contextvars(request_id="trace-xyz")

    get_logger("apps.test").info("order.created")

    assert captured()[0]["request_id"] == "trace-xyz"


def test_request_id_key_is_present_even_outside_a_request(captured):
    get_logger("apps.test").info("management.command_ran")

    assert captured()[0]["request_id"] == ""


def test_exception_is_rendered_into_the_payload(captured):
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        get_logger("apps.test").exception("request.unhandled_exception")

    payload = captured()[0]

    assert payload["level"] == "error"
    assert "RuntimeError: boom" in payload["exception"]


def test_a_plain_stdlib_record_is_rendered_as_json_too(captured):
    structlog.contextvars.bind_contextvars(request_id="trace-abc")

    logging.getLogger("thirdparty.library").warning("stdlib.line")

    payload = captured()[0]

    assert payload["event"] == "stdlib.line"
    assert payload["request_id"] == "trace-abc"


def test_a_uuid_in_a_request_log_line_is_redacted():
    # ADR 0003: the order access_token is a bearer credential and is never logged.
    # Django's log_response puts the request path into the message, and the token
    # is a path segment, so one unhandled 500 on the order page would leak it.
    token = "0f9c2a48-1d3e-4b7a-9c61-2f8e5d4a7b10"
    record = logging.LogRecord(
        name="django.request",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="%s: %s",
        args=("Internal Server Error", f"/api/v1/orders/{token}/"),
        exc_info=None,
    )

    assert RedactUUIDs().filter(record) is True
    assert token not in record.getMessage()
    assert "<redacted>" in record.getMessage()


def test_redaction_leaves_ordinary_paths_alone():
    record = logging.LogRecord(
        name="django.request",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="%s: %s",
        args=("Internal Server Error", "/api/v1/products/boxy-logo-tee/"),
        exc_info=None,
    )

    RedactUUIDs().filter(record)

    assert record.getMessage() == "Internal Server Error: /api/v1/products/boxy-logo-tee/"
