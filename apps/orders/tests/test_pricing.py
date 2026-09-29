from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory, ProductVariantFactory
from apps.orders.services import price_cart

pytestmark = pytest.mark.django_db


def _price(*, subtotal: str, district: str | None, quantity: int = 1):
    product = ProductFactory.create(is_published=True, base_price=Decimal(subtotal) / quantity)
    variant = ProductVariantFactory.create(product=product, stock_quantity=10)
    return price_cart(
        variants_by_id={variant.pk: variant},
        quantities={variant.pk: quantity},
        district=district,
    )


@pytest.mark.parametrize(
    ("district", "fee"),
    [("Lalitpur", "150.00"), (" kathmandu ", "150.00"), ("Pokhara", "250.00")],
)
def test_the_district_band_sets_the_fee(shipping_settings, district, fee):
    price = _price(subtotal="3200.00", district=district)

    assert price.shipping_fee == Decimal(fee)
    assert price.total == Decimal("3200.00") + Decimal(fee)


def test_lines_carry_unit_price_and_line_total(shipping_settings):
    price = _price(subtotal="6400.00", quantity=2, district="Lalitpur")

    (line,) = price.lines
    assert (line.quantity, line.unit_price, line.line_total) == (
        2,
        Decimal("3200.00"),
        Decimal("6400.00"),
    )
    assert price.subtotal == Decimal("6400.00")
    assert price.discount == Decimal("0.00")


def test_no_threshold_never_waives_the_fee(shipping_settings):
    price = _price(subtotal="99999.00", district="Pokhara")

    assert price.shipping_fee == Decimal("250.00")
    assert price.free_shipping_remaining is None


@pytest.mark.parametrize(
    ("subtotal", "fee", "remaining"),
    [
        ("7999.99", "150.00", "0.01"),
        ("8000.00", "0.00", None),
        ("8000.01", "0.00", None),
    ],
)
def test_the_threshold_boundary(shipping_settings, subtotal, fee, remaining):
    shipping_settings.free_shipping_threshold = Decimal("8000.00")
    shipping_settings.save()

    price = _price(subtotal=subtotal, district="Lalitpur")

    assert price.shipping_fee == Decimal(fee)
    assert price.total == Decimal(subtotal) + Decimal(fee)
    assert price.free_shipping_remaining == (None if remaining is None else Decimal(remaining))


def test_without_a_district_below_the_threshold_the_fee_and_total_are_unknown(
    shipping_settings,
):
    shipping_settings.free_shipping_threshold = Decimal("8000.00")
    shipping_settings.save()

    price = _price(subtotal="6400.00", district=None)

    assert price.shipping_fee is None
    assert price.total is None
    assert price.subtotal == Decimal("6400.00")
    assert price.free_shipping_remaining == Decimal("1600.00")


def test_without_a_district_at_the_threshold_shipping_is_free(shipping_settings):
    shipping_settings.free_shipping_threshold = Decimal("8000.00")
    shipping_settings.save()

    price = _price(subtotal="8000.00", district=None)

    assert price.shipping_fee == Decimal("0.00")
    assert price.total == Decimal("8000.00")
    assert price.free_shipping_remaining is None


def test_the_fees_come_from_the_settings_row(shipping_settings):
    shipping_settings.outside_valley_fee = Decimal("300.00")
    shipping_settings.save()

    assert _price(subtotal="1000.00", district="Pokhara").shipping_fee == Decimal("300.00")
