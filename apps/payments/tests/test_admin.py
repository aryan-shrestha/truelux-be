import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.urls import reverse

from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.tests.factories import OrderFactory
from apps.payments.models import Payment, PaymentStatus
from apps.payments.tests.factories import PaymentFactory
from apps.payments.tests.khalti_stubs import FakeResponse, lookup_body
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    staff = UserFactory.create(is_staff=True, is_superuser=True)
    client.force_login(staff)
    return client


def _act(admin_client, action, payments):
    return admin_client.post(
        reverse("admin:payments_payment_changelist"),
        {"action": action, ACTION_CHECKBOX_NAME: [str(payment.pk) for payment in payments]},
        follow=True,
    )


def _khalti_payment(**kwargs):
    order = OrderFactory.create(status=OrderStatus.PENDING, **kwargs)
    return PaymentFactory.create(
        order=order, method=PaymentMethod.KHALTI, pidx="pidx-1", amount=order.total
    )


def test_verify_action_marks_completed_payment_paid(admin_client, khalti_post):
    payment = _khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(total_amount=int(payment.amount * 100)))

    _act(admin_client, "verify_with_khalti", [payment])

    payment.refresh_from_db()
    payment.order.refresh_from_db()
    # ADR 0005's only recovery for a customer who paid and closed the tab: Khalti
    # sends no webhook, so nothing detects that payment until someone runs this.
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.order.status == OrderStatus.PAID


def test_verify_action_reports_a_failed_payment_without_raising(admin_client, khalti_post):
    payment = _khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(status="User canceled"), status_code=400)

    response = _act(admin_client, "verify_with_khalti", [payment])

    assert response.status_code == 200
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PENDING


def test_verify_action_skips_cash_payments_and_says_so(admin_client, khalti_post):
    cash = PaymentFactory.create()

    response = _act(admin_client, "verify_with_khalti", [cash])

    # A cash payment has no pidx, so there is nothing to look up and Khalti must
    # not be called with a null. Reported, because an action that appears to do
    # nothing gets run again.
    assert khalti_post.call_count == 0
    messages = [str(message) for message in response.context["messages"]]
    assert any("cash on delivery" in message for message in messages)


def test_mark_cash_collected_marks_the_order_paid(admin_client):
    order = OrderFactory.create(status=OrderStatus.PENDING)
    payment = PaymentFactory.create(order=order)

    _act(admin_client, "mark_cash_collected", [payment])

    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == PaymentStatus.COMPLETED
    assert order.status == OrderStatus.PAID


def test_collecting_an_already_collected_payment_is_reported_not_raised(admin_client):
    order = OrderFactory.create(status=OrderStatus.PENDING)
    payment = PaymentFactory.create(order=order, status=PaymentStatus.COMPLETED)

    response = _act(admin_client, "mark_cash_collected", [payment])

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_payments_cannot_be_added_by_hand(admin_client):
    response = admin_client.get(reverse("admin:payments_payment_add"))

    # One typed here would have no gateway record behind it and no order it was
    # taken against.
    assert response.status_code == 403


def test_payment_fields_are_read_only(admin_client):
    payment = PaymentFactory.create()

    response = admin_client.get(reverse("admin:payments_payment_change", args=[payment.pk]))

    assert b'name="status"' not in response.content
    assert b'name="amount"' not in response.content
    assert Payment.objects.count() == 1
