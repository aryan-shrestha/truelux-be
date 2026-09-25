import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.urls import reverse

from apps.payments.models import Payment, PaymentStatus
from apps.payments.tests.factories import PaymentFactory
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


def test_mark_cash_collected_completes_the_payment(admin_client):
    payment = PaymentFactory.create()

    _act(admin_client, "mark_cash_collected", [payment])

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.COMPLETED


def test_collecting_an_already_collected_payment_is_reported_not_raised(admin_client):
    payment = PaymentFactory.create(status=PaymentStatus.COMPLETED)

    response = _act(admin_client, "mark_cash_collected", [payment])

    assert response.status_code == 200
    messages = [str(message) for message in response.context["messages"]]
    assert any("Could not collect" in message for message in messages)


def test_payments_cannot_be_added_by_hand(admin_client):
    response = admin_client.get(reverse("admin:payments_payment_add"))

    assert response.status_code == 403


def test_payment_fields_are_read_only(admin_client):
    payment = PaymentFactory.create()

    response = admin_client.get(reverse("admin:payments_payment_change", args=[payment.pk]))

    assert b'name="status"' not in response.content
    assert b'name="amount"' not in response.content
    assert Payment.objects.count() == 1
