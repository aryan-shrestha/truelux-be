from decimal import Decimal

import pytest
import requests
from django.db import connection

from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.tests.factories import OrderFactory
from apps.payments.exceptions import (
    PaymentAmountMismatch,
    PaymentGatewayUnavailable,
    PaymentNotCompleted,
)
from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import initiate_khalti_payment, verify_khalti_payment
from apps.payments.tests.factories import PaymentFactory
from apps.payments.tests.khalti_stubs import FakeResponse, lookup_body

pytestmark = pytest.mark.django_db


def _pending_khalti_payment(**kwargs):
    order = OrderFactory.create(status=OrderStatus.PENDING, total=Decimal("4650.00"), **kwargs)
    return PaymentFactory.create(
        order=order, method=PaymentMethod.KHALTI, pidx="pidx-1", amount=order.total
    )


def test_initiate_records_a_pending_payment_and_returns_the_payment_url(khalti_post):
    order = OrderFactory.create(total=Decimal("4650.00"))

    payment_url = initiate_khalti_payment(order=order)

    assert payment_url == "https://test-pay.khalti.invalid/?pidx=pidx-1"
    payment = Payment.objects.get()
    assert payment.status == PaymentStatus.PENDING
    assert payment.method == PaymentMethod.KHALTI
    assert payment.pidx == "pidx-1"


def test_initiate_sends_the_order_number_as_the_purchase_order_id(khalti_post):
    order = OrderFactory.create()

    initiate_khalti_payment(order=order)

    payload = khalti_post.call_args.kwargs["json"]
    assert payload["purchase_order_id"] == order.order_number
    assert payload["purchase_order_name"] == f"Order {order.order_number}"


def test_initiate_failure_raises_naming_the_order(khalti_post):
    khalti_post.side_effect = requests.ConnectionError("no route to host")
    order = OrderFactory.create(status=OrderStatus.PENDING)

    with pytest.raises(PaymentGatewayUnavailable) as exc_info:
        initiate_khalti_payment(order=order)

    # The order is already committed and holding stock, so the customer must be
    # told it exists or they will check out again.
    assert exc_info.value.details["order_number"] == order.order_number
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING
    assert not Payment.objects.exists()


def test_a_lookup_failure_is_translated_for_the_browser(khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.side_effect = requests.ConnectionError("no route to host")

    # A raw KhaltiError would reach the handler as a 500 JSON page for a customer
    # who has just paid. As a DomainError it becomes the failure redirect instead.
    with pytest.raises(PaymentGatewayUnavailable):
        verify_khalti_payment(pidx="pidx-1")

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING


def test_a_lookup_missing_total_amount_does_not_fulfil(khalti_post):
    payment = _pending_khalti_payment()
    body = lookup_body()
    del body["total_amount"]
    khalti_post.return_value = FakeResponse(body)

    with pytest.raises(PaymentGatewayUnavailable):
        verify_khalti_payment(pidx="pidx-1")

    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PENDING


def test_completed_lookup_marks_the_order_paid(khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body())

    verified = verify_khalti_payment(pidx="pidx-1")

    assert verified.status == PaymentStatus.COMPLETED
    assert verified.transaction_id == "txn-1"
    assert verified.raw_status == "Completed"
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PAID


@pytest.mark.parametrize(
    "gateway_status",
    ["Pending", "Initiated", "Refunded", "Partially Refunded", "Expired", "User canceled"],
)
def test_only_completed_fulfils(khalti_post, gateway_status):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(status=gateway_status), status_code=400)

    with pytest.raises(PaymentNotCompleted) as exc_info:
        verify_khalti_payment(pidx="pidx-1")

    assert exc_info.value.details["gateway_status"] == gateway_status
    payment.refresh_from_db()
    payment.order.refresh_from_db()
    assert payment.status == PaymentStatus.FAILED
    # What Khalti said survives the refusal, or there is no trace to support from.
    assert payment.raw_status == gateway_status
    assert payment.order.status == OrderStatus.PENDING


def test_amount_mismatch_does_not_fulfil_and_is_logged_at_error(khalti_post, caplog):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(total_amount=100))

    with pytest.raises(PaymentAmountMismatch):
        verify_khalti_payment(pidx="pidx-1")

    payment.refresh_from_db()
    payment.order.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING
    assert payment.order.status == OrderStatus.PENDING
    assert "payment.amount_mismatch" in caplog.text


def test_a_second_verification_does_not_refulfil(khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body())
    verify_khalti_payment(pidx="pidx-1")
    khalti_post.reset_mock()

    again = verify_khalti_payment(pidx="pidx-1")

    assert again.status == PaymentStatus.COMPLETED
    # Khalti is not called again: the answer cannot change once it is Completed.
    assert khalti_post.call_count == 0
    assert Payment.objects.filter(status=PaymentStatus.COMPLETED).count() == 1
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PAID


def test_an_unknown_pidx_raises_rather_than_calling_khalti(khalti_post):
    with pytest.raises(Payment.DoesNotExist):
        verify_khalti_payment(pidx="never-issued")

    assert khalti_post.call_count == 0


def test_lookup_is_not_called_inside_transaction(khalti_post):
    """The other half of the constraint ADR 0004 and ADR 0005 share.

    `verify_khalti_payment` runs inside a customer's return request and takes a row
    lock to fulfil. Doing the lookup under that lock would hold it across an
    external call, and the return URL is a plain GET that customers refresh.

    Depth rather than `in_atomic_block`, because `django_db` wraps the test itself
    in an atomic block.
    """
    _pending_khalti_payment()
    depth_outside_the_service = len(connection.atomic_blocks)
    depth_at_call: list[int] = []

    def _post(*args, **kwargs):
        depth_at_call.append(len(connection.atomic_blocks))
        return FakeResponse(lookup_body())

    khalti_post.side_effect = _post

    verify_khalti_payment(pidx="pidx-1")

    assert depth_at_call == [depth_outside_the_service]
