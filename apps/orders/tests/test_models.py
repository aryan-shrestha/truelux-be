from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.orders.models import OrderItem, ShippingSettings
from apps.orders.selectors import get_shipping_settings
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


def test_the_data_migration_creates_the_default_shipping_settings():
    shipping = get_shipping_settings()

    assert shipping.inside_valley_fee == Decimal("150.00")
    assert shipping.outside_valley_fee == Decimal("250.00")
    assert shipping.free_shipping_threshold is None


def test_a_second_shipping_settings_row_violates_the_singleton_constraint(shipping_settings):
    with pytest.raises(IntegrityError):
        ShippingSettings.objects.create(
            id=2, inside_valley_fee=Decimal("1.00"), outside_valley_fee=Decimal("1.00")
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"inside_valley_fee": Decimal("-0.01")},
        {"outside_valley_fee": Decimal("-0.01")},
        {"free_shipping_threshold": Decimal("0.00")},
    ],
)
def test_shipping_settings_reject_negative_fees_and_a_zero_threshold(shipping_settings, fields):
    for name, value in fields.items():
        setattr(shipping_settings, name, value)

    with pytest.raises(IntegrityError):
        shipping_settings.save()
