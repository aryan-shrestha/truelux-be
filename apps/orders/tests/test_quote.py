from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

from apps.catalog.tests.factories import ProductFactory, ProductVariantFactory
from apps.orders.constants import PaymentMethod
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def _variant(*, stock=5, price=Decimal("3200.00"), published=True):
    product = ProductFactory.create(is_published=published, base_price=price)
    return ProductVariantFactory.create(product=product, stock_quantity=stock)


def _quote(api_client, **body):
    return api_client.post(reverse("v1:checkout-quote"), body, format="json")


def _lines(variant, quantity=2):
    return [{"variant_id": str(variant.pk), "quantity": quantity}]


def test_the_quote_prices_the_cart(api_client, shipping_settings):
    shipping_settings.free_shipping_threshold = Decimal("8000.00")
    shipping_settings.save()
    variant = _variant()

    response = _quote(api_client, items=_lines(variant), district="Lalitpur")

    assert response.status_code == 200
    assert response.data == {
        "subtotal": "6400.00",
        "shipping_fee": "150.00",
        "discount": "0.00",
        "total": "6550.00",
        "free_shipping_remaining": "1600.00",
        "lines": [
            {
                "variant_id": str(variant.pk),
                "quantity": 2,
                "unit_price": "3200.00",
                "line_total": "6400.00",
            }
        ],
    }


@pytest.mark.parametrize("body", [{}, {"district": None}, {"district": ""}])
def test_without_a_district_the_fee_and_total_are_null(api_client, shipping_settings, body):
    response = _quote(api_client, items=_lines(_variant()), **body)

    assert response.status_code == 200
    assert response.data["subtotal"] == "6400.00"
    assert response.data["shipping_fee"] is None
    assert response.data["total"] is None
    assert response.data["free_shipping_remaining"] is None


def test_duplicate_lines_are_summed_as_checkout_sums_them(api_client, shipping_settings):
    variant = _variant()

    response = _quote(
        api_client,
        items=[{"variant_id": str(variant.pk), "quantity": 1}] * 2,
        district="Pokhara",
    )

    assert response.data["lines"][0]["quantity"] == 2
    assert response.data["total"] == "6650.00"


@pytest.mark.parametrize("threshold", [None, Decimal("5000.00"), Decimal("8000.00")])
@pytest.mark.parametrize("district", ["Kathmandu", "Pokhara"])
def test_the_quote_matches_the_order_checkout_places(
    api_client, shipping_settings, threshold, district
):
    shipping_settings.free_shipping_threshold = threshold
    shipping_settings.save()
    variant = _variant(stock=10)
    items = _lines(variant, quantity=2)

    quote = _quote(api_client, items=items, district=district).data
    checkout = api_client.post(
        reverse("v1:checkout"),
        {
            "items": items,
            "email": "customer@example.com",
            "phone": "9800000000",
            "full_name": "Asha Rai",
            "address_line": "1 Test Road",
            "city": "Kathmandu",
            "district": district,
            "payment_method": PaymentMethod.COD.value,
        },
        format="json",
    ).data

    assert {key: checkout[key] for key in ("subtotal", "shipping_fee", "total")} == {
        key: quote[key] for key in ("subtotal", "shipping_fee", "total")
    }


def test_the_quote_writes_nothing(api_client, shipping_settings):
    variant = _variant(stock=5)

    _quote(api_client, items=_lines(variant), district="Lalitpur")

    variant.refresh_from_db()
    assert variant.stock_quantity == 5
    assert not Order.objects.exists()
    assert mail.outbox == []


def test_the_quote_ignores_client_supplied_prices(api_client, shipping_settings):
    variant = _variant()

    response = _quote(
        api_client,
        items=[{"variant_id": str(variant.pk), "quantity": 1, "unit_price": "1.00"}],
        district="Lalitpur",
        total="1.00",
    )

    assert response.data["total"] == "3350.00"


@pytest.mark.parametrize(
    "items",
    [[], [{"variant_id": "not-a-uuid", "quantity": 1}], "missing"],
)
def test_a_malformed_cart_is_400(api_client, shipping_settings, items):
    body = {} if items == "missing" else {"items": items}

    response = _quote(api_client, **body)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_a_zero_quantity_is_400(api_client, shipping_settings):
    response = _quote(api_client, items=_lines(_variant(), quantity=0))

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_an_unpublished_variant_is_422_variant_unavailable(api_client, shipping_settings):
    response = _quote(api_client, items=_lines(_variant(published=False)))

    assert response.status_code == 422
    assert response.data["error"]["code"] == "variant_unavailable"


def test_an_inactive_brand_is_422_variant_unavailable(api_client, shipping_settings):
    variant = _variant()
    variant.product.brand.is_active = False
    variant.product.brand.save()

    response = _quote(api_client, items=_lines(variant))

    assert response.status_code == 422
    assert response.data["error"]["code"] == "variant_unavailable"


def test_an_unknown_variant_is_422_variant_unavailable(api_client, shipping_settings):
    response = _quote(
        api_client, items=[{"variant_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]
    )

    assert response.status_code == 422
    assert response.data["error"]["code"] == "variant_unavailable"


def test_a_shortfall_is_422_insufficient_stock_without_the_count(api_client, shipping_settings):
    variant = _variant(stock=1)

    response = _quote(api_client, items=_lines(variant, quantity=2))

    assert response.status_code == 422
    assert response.data["error"]["code"] == "insufficient_stock"
    assert "available" not in response.data["error"]["details"]


def test_the_quote_shares_the_checkout_throttle(api_client, shipping_settings):
    items = _lines(_variant(stock=50), quantity=1)

    with mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, "checkout": "2/minute"},
    ):
        statuses = [_quote(api_client, items=items).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_shipping_serves_the_merchant_settings(api_client, shipping_settings):
    shipping_settings.free_shipping_threshold = Decimal("8000.00")
    shipping_settings.save()

    response = api_client.get(reverse("v1:shipping"))

    assert response.status_code == 200
    assert response.data == {
        "inside_valley_fee": "150.00",
        "outside_valley_fee": "250.00",
        "free_shipping_threshold": "8000.00",
    }


def test_shipping_serves_a_null_threshold_when_none_is_set(api_client, shipping_settings):
    response = api_client.get(reverse("v1:shipping"))

    assert response.data["free_shipping_threshold"] is None


def test_shipping_uses_the_catalog_throttle(api_client, shipping_settings):
    with mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, "catalog": "1/minute"},
    ):
        statuses = [api_client.get(reverse("v1:shipping")).status_code for _ in range(2)]

    assert statuses == [200, 429]
