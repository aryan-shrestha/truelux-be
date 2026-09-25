import threading
from decimal import Decimal

import pytest
from django.db import connections

from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.tests.factories import OrderFactory
from apps.payments.exceptions import PaymentAlreadyProcessed
from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import complete_cod_payment, record_cod_payment
from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


def test_cod_payment_records_pending_and_leaves_order_pending():
    order = OrderFactory.create(status=OrderStatus.PENDING, total=Decimal("4650.00"))

    payment = record_cod_payment(order=order)

    assert payment.status == PaymentStatus.PENDING
    assert payment.method == PaymentMethod.COD
    assert payment.amount == Decimal("4650.00")
    order.refresh_from_db()
    assert order.status == OrderStatus.PENDING


def test_complete_cod_payment_leaves_the_order_status_alone():
    order = OrderFactory.create(status=OrderStatus.DELIVERED)
    payment = PaymentFactory.create(order=order)

    completed = complete_cod_payment(payment=payment)

    assert completed.status == PaymentStatus.COMPLETED
    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERED


def test_completing_an_already_completed_payment_raises_payment_already_processed():
    payment = PaymentFactory.create(status=PaymentStatus.COMPLETED)

    with pytest.raises(PaymentAlreadyProcessed):
        complete_cod_payment(payment=payment)


# transaction=True: the other thread runs on its own connection and cannot see data
# held in an uncommitted test transaction.
@pytest.mark.django_db(transaction=True)
def test_concurrent_completion_completes_once():
    payment = PaymentFactory.create()

    start = threading.Barrier(2)
    failures: list[Exception] = []

    def collect_the_cash() -> None:
        try:
            start.wait(timeout=10)
            complete_cod_payment(payment=payment)
        except Exception as exc:  # noqa: BLE001 - the race's loser is the assertion
            failures.append(exc)
        finally:
            # A thread's connection left open holds a session and breaks teardown.
            connections.close_all()

    staff = [threading.Thread(target=collect_the_cash) for _ in range(2)]
    for thread in staff:
        thread.start()
    for thread in staff:
        thread.join(timeout=30)

    assert [type(failure) for failure in failures] == [PaymentAlreadyProcessed]
    assert Payment.objects.filter(status=PaymentStatus.COMPLETED).count() == 1
