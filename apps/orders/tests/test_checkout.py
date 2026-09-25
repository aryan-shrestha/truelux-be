import threading
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import (
    ProductFactory,
    ProductVariantFactory,
    ShadeFactory,
    SizeFactory,
)
from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.exceptions import EmptyCart
from apps.orders.models import Order, OrderItem
from apps.orders.services import place_order
from apps.payments.models import Payment, PaymentStatus

pytestmark = pytest.mark.django_db


def _payload(*, items, **overrides):
    payload = {
        "items": items,
        "email": "customer@example.com",
        "phone": "9800000000",
        "full_name": "Asha Rai",
        "address_line": "1 Test Road",
        "city": "Kathmandu",
        "district": "Kathmandu",
        "payment_method": PaymentMethod.COD.value,
    }
    payload.update(overrides)
    return payload


def _variant(*, stock=5, price=Decimal("4500.00"), published=True, **kwargs):
    product = ProductFactory.create(is_published=published, base_price=price)
    return ProductVariantFactory.create(product=product, stock_quantity=stock, **kwargs)


def _checkout(api_client, *, items, **overrides):
    return api_client.post(reverse("v1:checkout"), _payload(items=items, **overrides))


def test_checkout_creates_order_and_returns_201(api_client):
    variant = _variant()

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 2}])

    assert response.status_code == 201
    order = Order.objects.get(order_number=response.data["order_number"])
    assert order.status == OrderStatus.PENDING
    assert order.email == "customer@example.com"
    assert order.items.count() == 1


def test_checkout_decrements_variant_stock(api_client):
    variant = _variant(stock=5)

    _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 2}])

    variant.refresh_from_db()
    assert variant.stock_quantity == 3


def test_checkout_ignores_client_supplied_price(api_client):
    variant = _variant(price=Decimal("4500.00"))

    response = _checkout(
        api_client,
        items=[{"variant_id": str(variant.pk), "quantity": 1, "unit_price": "1.00"}],
        subtotal="1.00",
        total="1.00",
    )

    assert response.data["subtotal"] == "4500.00"
    assert response.data["total"] == "4650.00"
    assert OrderItem.objects.get().unit_price == Decimal("4500.00")


def test_checkout_snapshots_name_size_and_price_onto_items(api_client):
    size = SizeFactory.create(name="30 ml", slug="30-ml")
    shade = ShadeFactory.create(name="Warm Beige", slug="warm-beige")
    product = ProductFactory.create(
        is_published=True, name="Silk Foundation", base_price=Decimal("4500.00")
    )
    variant = ProductVariantFactory.create(
        product=product, size=size, shade=shade, sku="LUM-SF-30-WB", stock_quantity=5
    )

    _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    item = OrderItem.objects.get()
    assert item.product_name == "Silk Foundation"
    assert item.variant_size == "30 ml"
    assert item.variant_shade == "Warm Beige"
    assert item.sku == "LUM-SF-30-WB"
    assert item.unit_price == Decimal("4500.00")


def test_checkout_snapshots_an_empty_shade_for_a_shadeless_variant(api_client):
    variant = _variant()

    _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    assert OrderItem.objects.get().variant_shade == ""


def test_a_variant_of_an_inactive_brand_returns_422(api_client):
    variant = _variant()
    variant.product.brand.is_active = False
    variant.product.brand.save()

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    assert response.status_code == 422
    assert response.data["error"]["code"] == "variant_unavailable"


def test_checkout_uses_the_variant_price_override_when_set(api_client):
    product = ProductFactory.create(is_published=True, base_price=Decimal("4500.00"))
    variant = ProductVariantFactory.create(
        product=product, stock_quantity=5, price_override=Decimal("5200.00")
    )

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    assert response.data["subtotal"] == "5200.00"


def test_checkout_beyond_available_stock_returns_422(api_client):
    variant = _variant(stock=2)

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 3}])

    assert response.status_code == 422
    assert response.data["error"]["code"] == "insufficient_stock"
    assert response.data["error"]["details"]["variant_id"] == str(variant.pk)
    variant.refresh_from_db()
    assert variant.stock_quantity == 2


def test_unavailable_line_places_no_order_at_all(api_client):
    plenty = _variant(stock=10)
    scarce = ProductVariantFactory.create(product=plenty.product, stock_quantity=1)

    response = _checkout(
        api_client,
        items=[
            {"variant_id": str(plenty.pk), "quantity": 1},
            {"variant_id": str(scarce.pk), "quantity": 5},
        ],
    )

    assert response.status_code == 422
    plenty.refresh_from_db()
    assert plenty.stock_quantity == 10
    assert not Order.objects.exists()
    assert not OrderItem.objects.exists()


def test_unpublished_variant_returns_422(api_client):
    variant = _variant(published=False)

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    assert response.status_code == 422
    assert response.data["error"]["code"] == "variant_unavailable"
    assert not Order.objects.exists()


def test_unknown_variant_returns_422(api_client):
    response = _checkout(
        api_client,
        items=[{"variant_id": "11111111-1111-1111-1111-111111111111", "quantity": 1}],
    )

    assert response.status_code == 422
    assert response.data["error"]["code"] == "variant_unavailable"


def test_empty_cart_returns_400(api_client):
    response = _checkout(api_client, items=[])

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_zero_quantity_returns_400_not_500(api_client):
    variant = _variant()

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 0}])

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    variant.refresh_from_db()
    assert variant.stock_quantity == 5


def test_duplicate_cart_lines_for_one_variant_are_summed(api_client):
    variant = _variant(stock=5)

    response = _checkout(
        api_client,
        items=[
            {"variant_id": str(variant.pk), "quantity": 2},
            {"variant_id": str(variant.pk), "quantity": 1},
        ],
    )

    assert response.status_code == 201
    variant.refresh_from_db()
    assert variant.stock_quantity == 2
    assert OrderItem.objects.get().quantity == 3
    assert response.data["subtotal"] == "13500.00"


@pytest.mark.parametrize(
    ("district", "expected_fee"),
    [
        ("Kathmandu", "150.00"),
        ("lalitpur", "150.00"),
        ("Pokhara", "250.00"),
        ("Kathmandoo", "250.00"),
    ],
)
def test_shipping_fee_is_charged_by_district_band(api_client, district, expected_fee):
    variant = _variant()

    response = _checkout(
        api_client,
        items=[{"variant_id": str(variant.pk), "quantity": 1}],
        district=district,
    )

    assert response.data["shipping_fee"] == expected_fee
    assert response.data["total"] == str(Decimal("4500.00") + Decimal(expected_fee))


def test_checkout_response_never_contains_access_token(api_client):
    variant = _variant()

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    order = Order.objects.get()
    assert str(order.access_token) not in str(response.data)
    assert "access_token" not in response.data


def test_cod_checkout_records_a_pending_payment(api_client):
    variant = _variant()

    response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    payment = Payment.objects.get()
    assert payment.status == PaymentStatus.PENDING
    assert payment.method == PaymentMethod.COD
    assert payment.amount == Decimal(response.data["total"])
    assert payment.order.order_number == response.data["order_number"]


def test_a_failed_cod_record_leaves_an_order_with_no_payment(api_client):
    """The gap `payments.md` documents and nothing asserted.

    `record_cod_payment` runs after `place_order` has committed, so a failure here
    cannot roll the order back. The customer sees a 500 for an order that exists
    and holds stock, and `PaymentAdmin.has_add_permission` is False, so the
    merchant cannot create the missing row by hand either. Recorded here so the
    state is a known one rather than a surprise.
    """
    variant = _variant()

    with mock.patch(
        "apps.orders.views.record_cod_payment", side_effect=RuntimeError("database gone")
    ):
        response = _checkout(api_client, items=[{"variant_id": str(variant.pk), "quantity": 1}])

    assert response.status_code == 500
    assert response.data["error"]["code"] == "server_error"

    order = Order.objects.get()
    assert order.status == OrderStatus.PENDING
    assert not Payment.objects.filter(order=order).exists()
    variant.refresh_from_db()
    assert variant.stock_quantity == 4


def test_an_unknown_payment_method_returns_400(api_client):
    variant = _variant()

    response = _checkout(
        api_client,
        items=[{"variant_id": str(variant.pk), "quantity": 1}],
        payment_method="khalti",
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_exceeding_checkout_throttle_returns_429(api_client):
    variant = _variant(stock=50)
    items = [{"variant_id": str(variant.pk), "quantity": 1}]

    with mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, "checkout": "2/minute"},
    ):
        statuses = [_checkout(api_client, items=items).status_code for _ in range(3)]

    assert statuses == [201, 201, 429]


def test_place_order_with_no_items_raises_empty_cart():
    # Unreachable over HTTP (the serializer answers 400 first), but a service can be
    # called directly, and an empty cart would write an order with no lines.
    with pytest.raises(EmptyCart):
        place_order(
            items=[],
            email="customer@example.com",
            phone="9800000000",
            full_name="Asha Rai",
            address_line="1 Test Road",
            city="Kathmandu",
            district="Kathmandu",
            payment_method=PaymentMethod.COD.value,
        )

    assert not Order.objects.exists()


def _checkout_query_count(api_client, cart_size):
    product = ProductFactory.create(is_published=True)
    items = [
        {
            "variant_id": str(ProductVariantFactory.create(product=product, stock_quantity=9).pk),
            "quantity": 1,
        }
        for _ in range(cart_size)
    ]

    with CaptureQueriesContext(connection) as captured:
        response = api_client.post(reverse("v1:checkout"), _payload(items=items))

    assert response.status_code == 201, response.data
    return len(captured)


def test_each_extra_cart_line_costs_exactly_one_query(api_client):
    one_line = _checkout_query_count(api_client, 1)
    three_lines = _checkout_query_count(api_client, 3)

    # The only per-line cost is the stock UPDATE, which is inherent: N rows change,
    # so N rows are written. Everything else -- the locked fetch with its product,
    # size and shade joins, the order insert, the bulk_create of the lines -- is
    # one query whatever the cart holds. If this grows to three per line, the
    # select_related on size and shade has been dropped and the snapshot is doing
    # two extra queries per variant while holding every lock in the cart.
    assert three_lines - one_line == 2


# transaction=True, overriding the module marker: the other thread runs on its own
# connection and cannot see data held in an uncommitted test transaction.
@pytest.mark.django_db(transaction=True)
def test_concurrent_checkout_for_last_unit_places_one_order():
    variant = _variant(stock=1)
    items = [{"variant_id": str(variant.pk), "quantity": 1}]
    codes: list[int] = []
    start = threading.Barrier(2)

    def buy() -> None:
        try:
            start.wait(timeout=10)
            codes.append(
                APIClient().post(reverse("v1:checkout"), _payload(items=items)).status_code
            )
        finally:
            # Each thread opens its own connection. Leaving one open holds a session
            # on the test database and makes its teardown fail.
            connections.close_all()

    buyers = [threading.Thread(target=buy) for _ in range(2)]
    for buyer in buyers:
        buyer.start()
    for buyer in buyers:
        buyer.join(timeout=30)

    variant.refresh_from_db()
    assert sorted(codes) == [201, 422]
    assert variant.stock_quantity == 0
    assert Order.objects.count() == 1
    assert ProductVariant.objects.filter(pk=variant.pk, stock_quantity__lt=0).count() == 0
