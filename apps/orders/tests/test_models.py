from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.orders.models import OrderItem
from apps.orders.tests.factories import OrderFactory, OrderItemFactory

pytestmark = pytest.mark.django_db


def test_zero_quantity_item_violates_constraint():
    with pytest.raises(IntegrityError):
        OrderItemFactory.create(quantity=0)


def test_negative_total_violates_constraint():
    with pytest.raises(IntegrityError):
        OrderFactory.create(total=Decimal("-1.00"))


def test_duplicate_order_number_violates_constraint():
    order = OrderFactory.create()

    with pytest.raises(IntegrityError):
        OrderFactory.create(order_number=order.order_number)


def test_every_order_gets_a_distinct_access_token():
    first = OrderFactory.create()
    second = OrderFactory.create()

    assert first.access_token != second.access_token


def test_deleting_an_order_cascades_to_its_items():
    item = OrderItemFactory.create()

    item.order.delete()

    assert not OrderItem.objects.filter(pk=item.pk).exists()


def test_deleting_an_ordered_variant_is_protected():
    item = OrderItemFactory.create()

    with pytest.raises(ProtectedError):
        item.variant.delete()
