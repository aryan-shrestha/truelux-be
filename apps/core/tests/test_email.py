from unittest import mock

import pytest
from django.core import mail

from apps.core.email import send_email

TEMPLATE = "orders/email/order_confirmation"


def _context():
    order = mock.Mock()
    order.full_name = "Asha Rai"
    order.order_number = "TL-2026-000142"
    order.subtotal = "4500.00"
    order.shipping_fee = "150.00"
    order.total = "4650.00"
    order.payment_method = "cod"
    order.address_line = "1 Test Road"
    order.city = "Kathmandu"
    order.district = "Kathmandu"
    order.phone = "9800000000"
    return {"order": order, "items": [], "order_url": "https://storefront.invalid/orders/abc"}


def _send(**overrides):
    kwargs = {
        "to": "customer@example.com",
        "subject": "Order received",
        "template_name": TEMPLATE,
        "context": _context(),
        "reference": "TL-2026-000142",
    }
    kwargs.update(overrides)
    return send_email(**kwargs)


def test_send_email_renders_html_and_text_bodies():
    assert _send() is True

    message = mail.outbox[0]
    assert message.to == ["customer@example.com"]
    # A text body and an HTML alternative, not one or the other: a client that
    # refuses HTML must still get something readable.
    assert "TL-2026-000142" in message.body
    content, mimetype = message.alternatives[0]
    assert mimetype == "text/html"
    assert "TL-2026-000142" in content


def test_the_text_body_has_no_leading_blank_line():
    # A template opening with {% autoescape off %} renders one, and the customer
    # is what reads the result.
    _send()

    body = mail.outbox[0].body
    assert not body.startswith("\n")
    assert body.endswith("\n")


def test_the_text_body_is_not_html_escaped():
    context = _context()
    context["order"].full_name = "Ben & Jerry"

    _send(context=context)

    # Plain-text templates escape like any other unless told not to.
    assert "Ben & Jerry" in mail.outbox[0].body
    assert "&amp;" not in mail.outbox[0].body


def test_send_email_swallows_backend_failure():
    with mock.patch(
        "django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp is down")
    ):
        # ADR 0006: a customer whose order was placed must not see an error
        # because the mail server was slow.
        assert _send() is False

    assert mail.outbox == []


def test_send_email_swallows_a_template_failure():
    # Distinct from a send failure: rendering happens before the message exists,
    # and an exception here would escape the on_commit callback after the
    # transaction had already committed.
    assert _send(template_name="orders/email/no_such_template") is False

    assert mail.outbox == []


def test_send_email_logs_failure_at_error_level(caplog):
    with mock.patch(
        "django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp is down")
    ):
        _send()

    # The only trace the failure leaves: nothing retries and nothing alerts.
    assert "email.send_failed" in caplog.text
    assert any(record.levelname == "ERROR" for record in caplog.records)


def test_send_email_does_not_log_recipient_address(caplog):
    with mock.patch(
        "django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp is down")
    ):
        _send(to="private.person@example.com")

    # convention.md's never-log list is explicit about addresses.
    assert "private.person@example.com" not in caplog.text
    assert "TL-2026-000142" in caplog.text


def test_send_email_does_not_log_the_recipient_on_success(caplog):
    _send(to="private.person@example.com")

    assert "private.person@example.com" not in caplog.text
    assert "email.sent" in caplog.text


@pytest.mark.parametrize(
    "template", ["orders/email/order_confirmation", "orders/email/order_shipped"]
)
def test_both_templates_render(template):
    assert _send(template_name=template) is True
