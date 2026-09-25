from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.payments.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


def test_negative_amount_violates_constraint():
    with pytest.raises(IntegrityError):
        PaymentFactory.create(amount=Decimal("-1.00"))


def test_deleting_an_order_with_a_payment_is_protected():
    payment = PaymentFactory.create()

    with pytest.raises(ProtectedError):
        payment.order.delete()
