from decimal import Decimal
from typing import Any
from unittest import mock

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core import mail
from django.db import transaction
from django.urls import reverse

from apps.catalog.tests.factories import ProductFactory, ProductVariantFactory
from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.services import (
    confirm_order,
    mark_order_delivered,
    mark_order_shipped,
    place_order,
)
from apps.orders.tests.factories import OrderFactory, OrderItemFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    staff = UserFactory.create(is_staff=True, is_superuser=True)
    client.force_login(staff)
    return client


def _cart(stock=5):
    product = ProductFactory.create(is_published=True, base_price=Decimal("4500.00"))
    variant = ProductVariantFactory.create(product=product, stock_quantity=stock)
    return variant


def _place(variant, **overrides):
    # Annotated because mypy infers a narrow value type from the literal and then
    # rejects the ** expansion into place_order's heterogeneous signature.
    kwargs: dict[str, Any] = {
        "items": [{"variant_id": variant.pk, "quantity": 1}],
        "email": "customer@example.com",
        "phone": "9800000000",
        "full_name": "Asha Rai",
        "address_line": "1 Test Road",
        "city": "Kathmandu",
        "district": "Kathmandu",
        "payment_method": PaymentMethod.COD.value,
    }
    kwargs.update(overrides)
    return place_order(**kwargs)


def test_confirmation_is_sent_after_commit(django_capture_on_commit_callbacks):
    variant = _cart()

    with django_capture_on_commit_callbacks(execute=True):
        order = _place(variant)

    assert len(mail.outbox) == 1
    assert order.order_number in mail.outbox[0].subject


def test_confirmation_is_not_sent_before_the_transaction_commits():
    # Without django_capture_on_commit_callbacks the callback never runs, which is
    # exactly what on_commit promises: nothing leaves until the order is durable.
    variant = _cart()

    _place(variant)

    assert mail.outbox == []


def test_confirmation_is_not_sent_when_transaction_rolls_back(
    django_capture_on_commit_callbacks,
):
    # The test that proves ADR 0006 holds. If it starts failing, someone moved the
    # send inside the transaction, and an SMTP timeout can now destroy a placed
    # order whose stock is already decremented.
    variant = _cart()

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(RuntimeError),
        transaction.atomic(),
    ):
        _place(variant)
        raise RuntimeError("something after placement failed")

    assert mail.outbox == []
    variant.refresh_from_db()
    assert variant.stock_quantity == 5


def test_confirmation_contains_order_access_link(django_capture_on_commit_callbacks, settings):
    variant = _cart()

    with django_capture_on_commit_callbacks(execute=True):
        order = _place(variant)

    link = f"{settings.STOREFRONT_URL}/orders/{order.access_token}"
    message = mail.outbox[0]
    assert link in message.body
    assert link in message.alternatives[0][0]


def test_the_access_token_appears_only_inside_the_link(
    django_capture_on_commit_callbacks, settings
):
    variant = _cart()

    with django_capture_on_commit_callbacks(execute=True):
        order = _place(variant)

    # It is a credential. Bare in the text body it is something a customer might
    # paste into a support chat without realising what it is.
    body = mail.outbox[0].body
    assert body.count(str(order.access_token)) == 1
    assert f"/orders/{order.access_token}" in body


def test_a_multi_unit_line_says_the_price_is_per_unit(django_capture_on_commit_callbacks):
    variant = _cart()

    with django_capture_on_commit_callbacks(execute=True):
        order = _place(variant, items=[{"variant_id": variant.pk, "quantity": 2}])

    item = order.items.get()
    message = mail.outbox[0]

    # Without "each" the figure sits where a line total belongs, and two of them
    # make the subtotal -- so the customer reads a receipt that does not add up.
    assert item.unit_price * 2 == order.subtotal
    assert f"Rs. {item.unit_price} each" in message.body
    assert f"Rs. {item.unit_price} each" in message.alternatives[0][0]


def test_the_shipped_email_parts_agree_about_prices(django_capture_on_commit_callbacks):
    order = OrderFactory.create(status=OrderStatus.CONFIRMED)
    OrderItemFactory.create(order=order, unit_price=Decimal("1234.00"))

    with django_capture_on_commit_callbacks(execute=True):
        mark_order_shipped(order=order)

    message = mail.outbox[0]

    # The text part lists no item prices, so the HTML part shares the partial with
    # prices switched off. Otherwise one message says two things, and which one the
    # customer reads depends on their client.
    assert "1234.00" not in message.body
    assert "1234.00" not in message.alternatives[0][0]


def test_shipped_email_is_sent_by_the_service_not_the_admin(
    django_capture_on_commit_callbacks,
):
    order = OrderFactory.create(status=OrderStatus.CONFIRMED)
    OrderItemFactory.create(order=order)

    with django_capture_on_commit_callbacks(execute=True):
        mark_order_shipped(order=order)

    # Registered inside the service, so every caller gets it: the admin action, a
    # shell session, and anything added later.
    assert len(mail.outbox) == 1
    assert "on its way" in mail.outbox[0].subject


def test_no_email_is_sent_for_the_other_transitions(django_capture_on_commit_callbacks):
    order = OrderFactory.create(status=OrderStatus.PENDING)

    with django_capture_on_commit_callbacks(execute=True):
        confirm_order(order=order)
    with django_capture_on_commit_callbacks(execute=True):
        mark_order_shipped(order=order)
        mark_order_delivered(order=order)

    # Only shipping notifies. Confirmed and delivered are not customer-facing events.
    assert len(mail.outbox) == 1


def test_email_failure_does_not_fail_checkout(django_capture_on_commit_callbacks):
    variant = _cart()

    with (
        mock.patch(
            "django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp is down")
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        order = _place(variant)

    # The order stands; the customer simply never hears about it. That is the
    # failure mode ADR 0006 accepts, and the resend action is its recovery.
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING
    variant.refresh_from_db()
    assert variant.stock_quantity == 4
    assert mail.outbox == []


def test_a_template_failure_does_not_fail_checkout(django_capture_on_commit_callbacks):
    # The other half of the failure surface. Rendering happens before any message
    # exists, so an exception there escapes the on_commit callback -- and by then
    # the transaction has committed and the stock is gone. The customer would see a
    # 500 for an order that was placed.
    variant = _cart()

    with (
        mock.patch("apps.core.email.render_to_string", side_effect=RuntimeError("bad")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        order = _place(variant)

    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING
    variant.refresh_from_db()
    assert variant.stock_quantity == 4
    assert mail.outbox == []


def test_resend_confirmation_action_sends_to_the_address_on_the_order(admin_client):
    order = OrderFactory.create(email="customer@example.com")
    OrderItemFactory.create(order=order)

    admin_client.post(
        reverse("admin:orders_order_changelist"),
        {
            "action": "resend_confirmation",
            ACTION_CHECKBOX_NAME: [str(order.pk)],
        },
        follow=True,
    )

    assert len(mail.outbox) == 1
    # Never a parameter: an action that could redirect this would be a way to take
    # someone else's order, since the message carries the access token.
    assert mail.outbox[0].to == ["customer@example.com"]


def test_resend_shipping_notice_action_sends(admin_client):
    order = OrderFactory.create(status=OrderStatus.SHIPPED)
    OrderItemFactory.create(order=order)

    admin_client.post(
        reverse("admin:orders_order_changelist"),
        {"action": "resend_shipping_notice", ACTION_CHECKBOX_NAME: [str(order.pk)]},
        follow=True,
    )

    assert len(mail.outbox) == 1
    assert "on its way" in mail.outbox[0].subject


def test_a_failed_resend_is_reported_to_the_merchant(admin_client):
    order = OrderFactory.create()
    OrderItemFactory.create(order=order)

    with mock.patch(
        "django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp is down")
    ):
        response = admin_client.post(
            reverse("admin:orders_order_changelist"),
            {"action": "resend_confirmation", ACTION_CHECKBOX_NAME: [str(order.pk)]},
            follow=True,
        )

    messages = [str(message) for message in response.context["messages"]]
    assert any(order.order_number in message and "Could not" in message for message in messages)
