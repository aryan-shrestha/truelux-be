from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.orders.constants import PaymentMethod
from apps.orders.tests.factories import OrderFactory
from apps.payments.models import Payment


class PaymentFactory(DjangoModelFactory[Payment]):
    class Meta:
        model = Payment

    order = factory.SubFactory(OrderFactory)
    method = PaymentMethod.COD
    amount = Decimal("4650.00")
