from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.orders.constants import PaymentMethod
from apps.payments.models import Payment
from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


def test_negative_amount_violates_constraint():
    with pytest.raises(IntegrityError):
        PaymentFactory.create(amount=Decimal("-1.00"))


def test_khalti_payment_without_pidx_violates_constraint():
    with pytest.raises(IntegrityError):
        PaymentFactory.create(method=PaymentMethod.KHALTI, pidx=None)


def test_khalti_payment_with_a_pidx_is_allowed():
    payment = PaymentFactory.create(method=PaymentMethod.KHALTI, pidx="pidx-1")

    assert payment.pidx == "pidx-1"


def test_many_cod_payments_may_have_a_null_pidx():
    # PostgreSQL treats NULLs as distinct, which is the only reason a unique column
    # can hold one per COD order.
    PaymentFactory.create_batch(3)

    assert Payment.objects.filter(pidx__isnull=True).count() == 3


def test_duplicate_pidx_violates_constraint():
    PaymentFactory.create(method=PaymentMethod.KHALTI, pidx="pidx-shared")

    with pytest.raises(IntegrityError):
        PaymentFactory.create(method=PaymentMethod.KHALTI, pidx="pidx-shared")


def test_deleting_an_order_with_a_payment_is_protected():
    payment = PaymentFactory.create()

    with pytest.raises(ProtectedError):
        payment.order.delete()
