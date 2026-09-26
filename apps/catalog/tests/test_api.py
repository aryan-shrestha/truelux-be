from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

from apps.catalog.tests.factories import (
    CategoryFactory,
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
    ShadeFactory,
    SizeFactory,
)

pytestmark = pytest.mark.django_db


def _rates(**overrides):
    return mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, **overrides},
    )


def _product_with_variants(*, variant_count: int = 2, **kwargs):
    product = ProductFactory(is_published=True, **kwargs)
    ProductImageFactory(product=product, is_primary=True)
    for _ in range(variant_count):
        ProductVariantFactory(product=product, stock_quantity=5)
    return product


def test_product_list_returns_200_for_anonymous_user(api_client):
    _product_with_variants(name="Rose Milk Cleanser")

    response = api_client.get(reverse("v1:product-list"))

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["name"] == "Rose Milk Cleanser"


def test_product_list_excludes_unpublished_products(api_client):
    ProductFactory(is_published=True, slug="visible")
    ProductFactory(is_published=False, slug="hidden")

    response = api_client.get(reverse("v1:product-list"))

    slugs = [result["slug"] for result in response.data["results"]]
    assert slugs == ["visible"]


def test_product_detail_returns_variants_and_images(api_client):
    product = _product_with_variants(slug="rose-milk-cleanser", base_price=Decimal("4500.00"))

    response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert response.status_code == 200
    assert response.data["slug"] == "rose-milk-cleanser"
    assert len(response.data["variants"]) == 2
    assert response.data["variants"][0]["price"] == "4500.00"
    assert len(response.data["images"]) == 1


def test_product_detail_for_unpublished_slug_returns_404(api_client):
    product = ProductFactory(is_published=False, slug="not-yet")

    response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_product_detail_for_unknown_slug_returns_404(api_client):
    response = api_client.get(reverse("v1:product-detail", args=["no-such-product"]))

    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


@pytest.mark.parametrize("product_count", [5, 20])
def test_product_list_query_count_is_constant(api_client, django_assert_num_queries, product_count):
    for _ in range(product_count):
        _product_with_variants()

    # count + page of products + images prefetch. `in_stock` is annotated and
    # `category` is joined, so neither adds a query as the page grows.
    with django_assert_num_queries(3):
        response = api_client.get(reverse("v1:product-list"))

    assert len(response.data["results"]) == product_count


@pytest.mark.parametrize("variant_count", [2, 6])
def test_product_detail_query_count_is_constant(
    api_client, django_assert_num_queries, variant_count
):
    product = _product_with_variants(variant_count=variant_count)

    # product + variants (size and shade joined) + images + skin types. Without the
    # inner select_related this grows by two per variant.
    with django_assert_num_queries(4):
        response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert len(response.data["variants"]) == variant_count


def test_product_serializer_does_not_expose_stock_quantity(api_client):
    product = _product_with_variants()

    list_response = api_client.get(reverse("v1:product-list"))
    detail_response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert "stock_quantity" not in str(list_response.data)
    assert "stock_quantity" not in str(detail_response.data)
    assert detail_response.data["variants"][0]["in_stock"] is True


def test_filter_by_size_returns_only_matching_products(api_client):
    medium = SizeFactory(name="30 ml", slug="30-ml")
    large = SizeFactory(name="L", slug="l")
    wanted = ProductFactory(is_published=True, slug="wanted")
    ProductVariantFactory(product=wanted, size=medium)
    unwanted = ProductFactory(is_published=True, slug="unwanted")
    ProductVariantFactory(product=unwanted, size=large)

    response = api_client.get(reverse("v1:product-list"), {"size": "30-ml"})

    slugs = [result["slug"] for result in response.data["results"]]
    assert slugs == ["wanted"]


def test_filter_by_size_does_not_duplicate_a_product_sold_in_several_shades(api_client):
    medium = SizeFactory(name="30 ml", slug="30-ml")
    product = ProductFactory(is_published=True)
    for _ in range(3):
        ProductVariantFactory(product=product, size=medium, shade=ShadeFactory())

    response = api_client.get(reverse("v1:product-list"), {"size": "30-ml"})

    assert response.data["count"] == 1


def test_in_stock_filter_does_not_duplicate_rows(api_client):
    product = ProductFactory(is_published=True)
    for _ in range(3):
        ProductVariantFactory(product=product, stock_quantity=4)
    sold_out = ProductFactory(is_published=True)
    ProductVariantFactory(product=sold_out, stock_quantity=0)

    response = api_client.get(reverse("v1:product-list"), {"in_stock": "true"})

    assert response.data["count"] == 1
    assert response.data["results"][0]["slug"] == product.slug


def test_filter_by_category_and_price_range(api_client):
    cleansers = CategoryFactory(slug="cleansers")
    wanted = ProductFactory(is_published=True, category=cleansers, base_price=Decimal("4500.00"))
    ProductFactory(is_published=True, category=cleansers, base_price=Decimal("9000.00"))
    ProductFactory(is_published=True, base_price=Decimal("4500.00"))

    response = api_client.get(
        reverse("v1:product-list"),
        {"category": "cleansers", "min_price": "1000", "max_price": "5000"},
    )

    slugs = [result["slug"] for result in response.data["results"]]
    assert slugs == [wanted.slug]


def test_search_matches_name_and_description(api_client):
    by_name = ProductFactory(is_published=True, name="Rose Milk Cleanser", slug="by-name")
    by_description = ProductFactory(
        is_published=True,
        name="Arctic Water Cream",
        slug="by-description",
        description="Made with rose water.",
    )
    ProductFactory(is_published=True, name="Kohl Kajal", slug="no-match")

    response = api_client.get(reverse("v1:product-list"), {"search": "rose"})

    slugs = {result["slug"] for result in response.data["results"]}
    assert slugs == {by_name.slug, by_description.slug}


def test_ordering_by_price_paginates_without_repeating_rows(api_client):
    for _ in range(4):
        ProductFactory(is_published=True, base_price=Decimal("4500.00"))

    first = api_client.get(reverse("v1:product-list"), {"ordering": "base_price", "limit": 2})
    second = api_client.get(
        reverse("v1:product-list"), {"ordering": "base_price", "limit": 2, "offset": 2}
    )

    slugs = [result["slug"] for result in first.data["results"] + second.data["results"]]
    assert len(set(slugs)) == 4


def test_variants_are_ordered_by_size_sort_order(api_client):
    product = ProductFactory(is_published=True)
    large = SizeFactory(name="L", slug="l", sort_order=3)
    small = SizeFactory(name="S", slug="s", sort_order=1)
    ProductVariantFactory(product=product, size=large)
    ProductVariantFactory(product=product, size=small)

    response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert [variant["size"]["name"] for variant in response.data["variants"]] == ["S", "L"]


def test_category_list_returns_roots_with_their_children(api_client, django_assert_num_queries):
    cleansers = CategoryFactory(name="Cleansers", slug="cleansers")
    CategoryFactory(name="Foaming", slug="foaming", parent=cleansers)
    CategoryFactory(name="Serums", slug="serums")

    # Roots plus the children prefetch, and no count query: the tree is unpaginated.
    with django_assert_num_queries(2):
        response = api_client.get(reverse("v1:category-list"))

    assert response.status_code == 200
    # Unpaginated, so navigation cannot be truncated by a page size.
    assert [category["slug"] for category in response.data] == ["cleansers", "serums"]
    assert [child["slug"] for child in response.data[0]["children"]] == ["foaming"]


def test_write_methods_are_not_routed(api_client):
    response = api_client.post(reverse("v1:product-list"), {"name": "Rose Milk Cleanser"})

    assert response.status_code == 405
    assert response.data["error"]["code"] == "method_not_allowed"


def test_exceeding_catalog_throttle_returns_429_with_throttled_code(api_client):
    url = reverse("v1:product-list")

    # THROTTLE_RATES is read onto the class at import, so the `settings` fixture
    # cannot reach it.
    with _rates(catalog="2/minute"):
        statuses = [api_client.get(url).status_code for _ in range(3)]
        response = api_client.get(url)

    assert statuses == [200, 200, 429]
    assert response.data["error"]["code"] == "throttled"


def test_the_catalog_scope_is_separate_from_the_global_anonymous_rate(api_client):
    url = reverse("v1:product-list")

    with _rates(anon="1/minute", catalog="1000/minute"):
        statuses = [api_client.get(url).status_code for _ in range(3)]

    assert statuses == [200, 200, 200]
