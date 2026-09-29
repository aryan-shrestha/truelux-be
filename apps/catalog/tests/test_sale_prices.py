from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.urls import reverse

from apps.catalog.exceptions import CompareAtNotAbovePrice
from apps.catalog.models import ProductVariant, discount_percent
from apps.catalog.services import create_variant, update_product, update_variant
from apps.catalog.tests.factories import (
    BrandFactory,
    CategoryFactory,
    ProductFactory,
    ProductVariantFactory,
    SizeFactory,
)

pytestmark = pytest.mark.django_db


def _variant(*, base_price="3200.00", price_override=None, compare_at=None, **kwargs):
    product = kwargs.pop("product", None) or ProductFactory(
        is_published=True, base_price=Decimal(base_price)
    )
    return ProductVariantFactory(
        product=product,
        price_override=Decimal(price_override) if price_override else None,
        compare_at_price=Decimal(compare_at) if compare_at else None,
        **kwargs,
    )


# --- The predicate --------------------------------------------------------------


def test_a_compare_at_above_the_base_price_is_on_sale():
    variant = _variant(base_price="2720.00", compare_at="3200.00")

    assert variant.on_sale is True
    assert variant.discount_percent == 15


def test_a_compare_at_above_the_override_price_is_on_sale():
    variant = _variant(base_price="5000.00", price_override="2720.00", compare_at="3200.00")

    assert variant.on_sale is True
    assert variant.discount_percent == 15


@pytest.mark.parametrize("compare_at", [None, "3200.00", "3000.00"])
def test_no_compare_at_or_one_at_or_below_the_price_is_not_on_sale(compare_at):
    variant = ProductVariant(
        product=ProductFactory.build(base_price=Decimal("3200.00")),
        compare_at_price=Decimal(compare_at) if compare_at else None,
    )

    assert variant.on_sale is False
    assert variant.discount_percent is None


@pytest.mark.parametrize(
    ("price", "compare_at", "percent"),
    [("2720.00", "3200.00", 15), ("850.00", "999.00", 14), ("0.01", "100.00", 99)],
)
def test_discount_percent_is_floored(price, compare_at, percent):
    assert discount_percent(price=Decimal(price), compare_at_price=Decimal(compare_at)) == percent


def test_the_database_refuses_a_compare_at_of_zero():
    variant = _variant()
    variant.compare_at_price = Decimal("0.00")

    with pytest.raises(IntegrityError):
        variant.save()


# --- The services ---------------------------------------------------------------


@pytest.mark.parametrize("compare_at", ["3200.00", "2000.00"])
def test_create_variant_rejects_a_compare_at_not_above_the_price(compare_at):
    product = ProductFactory.create(base_price=Decimal("3200.00"))

    with pytest.raises(CompareAtNotAbovePrice):
        create_variant(
            product=product,
            fields={
                "sku": "SALE-1",
                "size": SizeFactory(),
                "compare_at_price": Decimal(compare_at),
            },
        )

    assert not ProductVariant.objects.exists()


def test_update_variant_checks_the_compare_at_against_the_new_override():
    variant = _variant(base_price="3200.00")

    with pytest.raises(CompareAtNotAbovePrice):
        update_variant(
            variant=variant,
            fields={"price_override": Decimal("4000.00"), "compare_at_price": Decimal("3800.00")},
        )

    update_variant(
        variant=variant,
        fields={"price_override": Decimal("2720.00"), "compare_at_price": Decimal("3200.00")},
    )
    variant.refresh_from_db()
    assert variant.on_sale is True


def test_repricing_a_product_above_its_compare_at_is_allowed_and_ends_the_sale():
    variant = _variant(base_price="2720.00", compare_at="3200.00")

    update_product(product=variant.product, fields={"base_price": Decimal("3500.00")})

    variant.refresh_from_db()
    assert variant.compare_at_price == Decimal("3200.00")
    assert variant.on_sale is False


def test_raising_an_override_above_the_compare_at_is_allowed_and_ends_the_sale():
    variant = _variant(price_override="2720.00", compare_at="3200.00")

    update_variant(variant=variant, fields={"price_override": Decimal("3300.00")})

    variant.refresh_from_db()
    assert variant.on_sale is False


def test_clearing_the_compare_at_ends_the_sale():
    variant = _variant(base_price="2720.00", compare_at="3200.00")

    update_variant(variant=variant, fields={"compare_at_price": None})

    variant.refresh_from_db()
    assert variant.compare_at_price is None


# --- The public API -------------------------------------------------------------


def _list(api_client, **params):
    return api_client.get(reverse("v1:product-list"), params)


def test_a_product_on_sale_carries_its_sale_variant_on_list_and_detail(api_client):
    variant = _variant(base_price="2720.00", compare_at="3200.00")

    listed = _list(api_client).data["results"][0]
    detail = api_client.get(reverse("v1:product-detail", args=[variant.product.slug])).data

    for item in (listed, detail):
        assert item["on_sale"] is True
        assert item["sale_price"] == "2720.00"
        assert item["compare_at_price"] == "3200.00"
        assert item["discount_percent"] == 15
        assert item["base_price"] == "2720.00"
    assert detail["variants"][0]["compare_at_price"] == "3200.00"
    assert detail["variants"][0]["on_sale"] is True
    assert detail["variants"][0]["discount_percent"] == 15


def test_a_product_not_on_sale_has_null_sale_fields(api_client):
    variant = _variant(base_price="3200.00", compare_at="3200.00")

    listed = _list(api_client).data["results"][0]
    detail = api_client.get(reverse("v1:product-detail", args=[variant.product.slug])).data

    for item in (listed, detail):
        assert item["on_sale"] is False
        assert item["sale_price"] is None
        assert item["compare_at_price"] is None
        assert item["discount_percent"] is None
    assert detail["variants"][0]["compare_at_price"] == "3200.00"
    assert detail["variants"][0]["on_sale"] is False
    assert detail["variants"][0]["discount_percent"] is None


def test_the_sale_variant_is_the_cheapest_on_sale_variant(api_client):
    product = ProductFactory(is_published=True, base_price=Decimal("3000.00"))
    _variant(product=product, compare_at="3500.00")
    _variant(product=product, price_override="2500.00", compare_at="2600.00")
    _variant(product=product, price_override="2000.00")

    item = _list(api_client).data["results"][0]

    assert (item["sale_price"], item["compare_at_price"], item["discount_percent"]) == (
        "2500.00",
        "2600.00",
        3,
    )


def test_a_tie_on_price_goes_to_the_smaller_size(api_client):
    product = ProductFactory(is_published=True, base_price=Decimal("3000.00"))
    _variant(product=product, compare_at="4000.00", size=SizeFactory(sort_order=2))
    _variant(product=product, compare_at="3600.00", size=SizeFactory(sort_order=1))

    item = _list(api_client).data["results"][0]

    assert item["compare_at_price"] == "3600.00"


def test_on_sale_filter(api_client):
    on_sale = _variant(base_price="2720.00", compare_at="3200.00").product
    full_price = _variant(base_price="3200.00", compare_at="3200.00").product

    only_sale = _list(api_client, on_sale="true")
    no_sale = _list(api_client, on_sale="false")

    assert [p["slug"] for p in only_sale.data["results"]] == [on_sale.slug]
    assert [p["slug"] for p in no_sale.data["results"]] == [full_price.slug]


def test_on_sale_combines_with_brand_and_category(api_client):
    brand = BrandFactory(slug="anua")
    category = CategoryFactory(slug="cleanse")
    wanted = ProductFactory(
        is_published=True, brand=brand, category=category, base_price=Decimal("2720.00")
    )
    _variant(product=wanted, compare_at="3200.00")
    other_brand = ProductFactory(is_published=True, category=category, base_price=Decimal("1.00"))
    _variant(product=other_brand, compare_at="2.00")
    ProductVariantFactory(product=ProductFactory(is_published=True, brand=brand))

    response = _list(api_client, on_sale="true", brand="anua", category="cleanse")

    assert [p["slug"] for p in response.data["results"]] == [wanted.slug]


def test_a_product_with_several_sale_variants_is_listed_once(api_client):
    product = ProductFactory(is_published=True, base_price=Decimal("1000.00"))
    for _ in range(3):
        _variant(product=product, compare_at="1500.00")

    assert _list(api_client, on_sale="true").data["count"] == 1


@pytest.mark.parametrize("value", ["yes", "1", "True", "maybe"])
def test_an_invalid_on_sale_value_is_a_400(api_client, value):
    response = _list(api_client, on_sale=value)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert "on_sale" in response.data["error"]["details"]


@pytest.mark.parametrize("product_count", [5, 20])
def test_the_list_query_count_is_unchanged_with_sales(
    api_client, django_assert_num_queries, product_count
):
    for _ in range(product_count):
        _variant(base_price="2720.00", compare_at="3200.00")

    # count + page + images: the sale fields are subqueries in the page's SELECT.
    with django_assert_num_queries(3):
        response = _list(api_client, on_sale="true")

    assert len(response.data["results"]) == product_count
