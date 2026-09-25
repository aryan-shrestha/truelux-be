import threading
from decimal import Decimal

import pytest
from django.db import connections

from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.exceptions import InvalidStatusTransition
from apps.orders.tests.factories import OrderFactory
from apps.payments.exceptions import PaymentAlreadyProcessed
from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import complete_cod_payment, record_cod_payment
from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


def test_cod_payment_records_pending_and_leaves_order_unpaid():
    order = OrderFactory.create(status=OrderStatus.PENDING, total=Decimal("4650.00"))

    payment = record_cod_payment(order=order)

    assert payment.status == PaymentStatus.PENDING
    assert payment.method == PaymentMethod.COD
    assert payment.amount == Decimal("4650.00")
    assert payment.pidx is None
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_complete_cod_payment_marks_the_order_paid():
    order = OrderFactory.create(status=OrderStatus.PENDING)
    payment = PaymentFactory.create(order=order)

    completed = complete_cod_payment(payment=payment)

    assert completed.status == PaymentStatus.COMPLETED
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


def test_completing_an_already_completed_payment_raises_payment_already_processed():
    order = OrderFactory.create(status=OrderStatus.PENDING)
    payment = PaymentFactory.create(order=order, status=PaymentStatus.COMPLETED)

    with pytest.raises(PaymentAlreadyProcessed):
        complete_cod_payment(payment=payment)

    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_completing_a_payment_for_a_shipped_order_leaves_the_payment_pending():
    # The order transition guard is the orders service's, and it runs inside this
    # service's transaction -- so a rejected transition rolls the payment back
    # rather than leaving a completed payment against an order that never moved.
    order = OrderFactory.create(status=OrderStatus.SHIPPED)
    payment = PaymentFactory.create(order=order)

    with pytest.raises(InvalidStatusTransition):
        complete_cod_payment(payment=payment)

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING


# transaction=True, overriding the module marker: the other thread runs on its own
# connection and cannot see data held in an uncommitted test transaction.
@pytest.mark.django_db(transaction=True)
def test_concurrent_completion_marks_the_order_paid_once():
    order = OrderFactory.create(status=OrderStatus.PENDING)
    payment = PaymentFactory.create(order=order)

    start = threading.Barrier(2)
    failures: list[Exception] = []

    def collect_the_cash() -> None:
        try:
            start.wait(timeout=10)
            complete_cod_payment(payment=payment)
        except Exception as exc:  # noqa: BLE001 - the race's loser is the assertion
            failures.append(exc)
        finally:
            # Each thread opens its own connection. Leaving one open holds a session
            # on the test database and makes its teardown fail.
            connections.close_all()

    merchants = [threading.Thread(target=collect_the_cash) for _ in range(2)]
    for merchant in merchants:
        merchant.start()
    for merchant in merchants:
        merchant.join(timeout=30)

    order.refresh_from_db()
    assert order.status == OrderStatus.PAID
    assert [type(failure) for failure in failures] == [PaymentAlreadyProcessed]
    assert Payment.objects.filter(status=PaymentStatus.COMPLETED).count() == 1
