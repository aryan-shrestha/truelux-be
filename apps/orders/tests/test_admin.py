from unittest import mock

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core import mail
from django.urls import reverse

from apps.catalog.tests.factories import ProductVariantFactory
from apps.orders.admin import OrderAdmin
from apps.orders.constants import OrderStatus
from apps.orders.tests.factories import OrderFactory, OrderItemFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    staff = UserFactory.create(is_staff=True, is_superuser=True)
    client.force_login(staff)
    return client


def _act(admin_client, action, orders):
    return admin_client.post(
        reverse("admin:orders_order_changelist"),
        {"action": action, ACTION_CHECKBOX_NAME: [str(order.pk) for order in orders]},
        follow=True,
    )


def test_status_is_not_an_editable_form_field():
    # A naive status write would skip the transition guards and the shipping email.
    assert "status" in OrderAdmin.readonly_fields


def test_mark_shipped_action_moves_a_confirmed_order(admin_client):
    order = OrderFactory.create(status=OrderStatus.CONFIRMED)

    _act(admin_client, "mark_shipped", [order])

    order.refresh_from_db()
    assert order.status == OrderStatus.SHIPPED


def test_confirm_and_delivered_actions_move_an_order_along(admin_client):
    order = OrderFactory.create(status=OrderStatus.PENDING)

    _act(admin_client, "confirm", [order])
    _act(admin_client, "mark_shipped", [order])
    _act(admin_client, "mark_delivered", [order])

    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERED


def test_cancel_action_restores_variant_stock(admin_client):
    variant = ProductVariantFactory.create(stock_quantity=4)
    order = OrderFactory.create(status=OrderStatus.PENDING)
    OrderItemFactory.create(order=order, variant=variant, quantity=3)

    _act(admin_client, "cancel", [order])

    variant.refresh_from_db()
    order.refresh_from_db()
    assert variant.stock_quantity == 7
    assert order.status == OrderStatus.CANCELLED


def test_action_reports_partial_failure_without_raising(admin_client):
    movable = OrderFactory.create(status=OrderStatus.CONFIRMED)
    stuck = OrderFactory.create(status=OrderStatus.PENDING)

    response = _act(admin_client, "mark_shipped", [movable, stuck])

    # An unhandled exception halfway through leaves the merchant with a 500 and no
    # idea which orders were processed, so they run it again.
    assert response.status_code == 200
    movable.refresh_from_db()
    stuck.refresh_from_db()
    assert movable.status == OrderStatus.SHIPPED
    assert stuck.status == OrderStatus.PENDING

    messages = [str(message) for message in response.context["messages"]]
    assert any(movable.order_number in message for message in messages)
    assert any(stuck.order_number in message for message in messages)


def test_access_token_is_not_exposed_in_the_admin(admin_client):
    order = OrderFactory.create()
    OrderItemFactory.create(order=order)

    changelist = admin_client.get(reverse("admin:orders_order_changelist"))
    change = admin_client.get(reverse("admin:orders_order_change", args=[order.pk]))

    # It is a bearer credential, and the admin is the one place it would otherwise
    # be casually visible over someone's shoulder.
    token = str(order.access_token).encode()
    assert token not in changelist.content
    assert token not in change.content


def test_order_items_cannot_be_edited(admin_client):
    order = OrderFactory.create()
    OrderItemFactory.create(order=order, product_name="Rose Milk Cleanser")

    response = admin_client.get(reverse("admin:orders_order_change", args=[order.pk]))

    # Every line is a snapshot of what the customer bought; editing one rewrites
    # history.
    assert b'name="items-0-quantity"' not in response.content
    assert b"Rose Milk Cleanser" in response.content


def test_resend_action_reports_a_failed_send_without_raising(admin_client):
    """ADR 0006 retries nothing, so this action is a failed email's only recovery.

    A send that raises out of the action would give the merchant a 500 on the one
    page they go to when a customer says the email never arrived.
    """
    order = OrderFactory.create()
    OrderItemFactory.create(order=order)

    with mock.patch("apps.orders.emails.send_email", return_value=False):
        response = _act(admin_client, "resend_confirmation", [order])

    assert response.status_code == 200
    messages = [str(message) for message in response.context["messages"]]
    assert any(order.order_number in message for message in messages)
    assert any("Could not send" in message for message in messages)


def test_resend_actions_send_to_the_address_on_the_order(admin_client):
    # Neither action takes a recipient. The message carries the order's
    # access_token, so an action that could redirect it would be a way to read
    # someone else's order rather than a support tool.
    order = OrderFactory.create(email="customer@example.com", status=OrderStatus.SHIPPED)
    OrderItemFactory.create(order=order)

    _act(admin_client, "resend_confirmation", [order])
    _act(admin_client, "resend_shipping_notice", [order])

    assert [message.to for message in mail.outbox] == [["customer@example.com"]] * 2
