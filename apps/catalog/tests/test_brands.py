import pytest
from django.db.models import ProtectedError
from django.urls import reverse

from apps.catalog.tests.factories import (
    BrandFactory,
    ProductFactory,
    ProductVariantFactory,
    ShadeFactory,
    SizeFactory,
)
from apps.core.exceptions import api_exception_handler

pytestmark = pytest.mark.django_db


def test_brand_list_hides_inactive_brands_and_counts_published_products(api_client):
    lumiere = BrandFactory(name="Lumière", slug="lumiere", sort_order=1)
    BrandFactory(slug="retired", is_active=False)
    ProductFactory.create_batch(2, brand=lumiere, is_published=True)
    ProductFactory(brand=lumiere, is_published=False)

    response = api_client.get(reverse("v1:brand-list"))

    assert response.status_code == 200
    assert [brand["slug"] for brand in response.data] == ["lumiere"]
    assert response.data[0]["name"] == "Lumière"
    assert response.data[0]["product_count"] == 2
    assert response.data[0]["logo_url"] is None


def test_brand_list_is_ordered_by_sort_order_then_name(api_client):
    BrandFactory(name="Zeta", slug="zeta", sort_order=0)
    BrandFactory(name="Beta", slug="beta", sort_order=1)
    BrandFactory(name="Alpha", slug="alpha", sort_order=1)

    response = api_client.get(reverse("v1:brand-list"))

    assert [brand["slug"] for brand in response.data] == ["zeta", "alpha", "beta"]


def test_brand_logo_url_is_the_storage_url(api_client):
    BrandFactory(slug="aurum", logo="brands/aurum.png")

    response = api_client.get(reverse("v1:brand-detail", args=["aurum"]))

    assert response.data["logo_url"].endswith("brands/aurum.png")


def test_brand_detail_returns_the_list_item_shape(api_client):
    BrandFactory(slug="lumiere", description="French-inspired complexion care.")

    response = api_client.get(reverse("v1:brand-detail", args=["lumiere"]))

    assert response.status_code == 200
    assert set(response.data) == {"name", "slug", "description", "logo_url", "product_count"}


def test_unknown_and_inactive_brand_slugs_return_the_same_404(api_client):
    BrandFactory(slug="retired", is_active=False)

    inactive = api_client.get(reverse("v1:brand-detail", args=["retired"]))
    unknown = api_client.get(reverse("v1:brand-detail", args=["no-such-brand"]))

    assert inactive.status_code == unknown.status_code == 404
    assert inactive.data == unknown.data


def test_product_items_carry_their_brand(api_client):
    brand = BrandFactory(name="Lumière", slug="lumiere")
    product = ProductFactory(brand=brand, is_published=True)

    listing = api_client.get(reverse("v1:product-list"))
    detail = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert listing.data["results"][0]["brand"] == {"name": "Lumière", "slug": "lumiere"}
    assert detail.data["brand"] == {"name": "Lumière", "slug": "lumiere"}


def test_repeated_brand_filter_returns_the_union(api_client):
    for slug in ("lumiere", "verde", "aurum"):
        ProductFactory(brand=BrandFactory(slug=slug), slug=f"{slug}-product", is_published=True)

    response = api_client.get(reverse("v1:product-list"), {"brand": ["lumiere", "verde"]})

    slugs = {result["slug"] for result in response.data["results"]}
    assert slugs == {"lumiere-product", "verde-product"}


def test_an_inactive_brand_hides_its_products_everywhere(api_client):
    brand = BrandFactory(slug="retired", is_active=False)
    product = ProductFactory(brand=brand, is_published=True)
    ProductVariantFactory(product=product, size=SizeFactory(slug="50-ml"), shade=ShadeFactory())

    listing = api_client.get(reverse("v1:product-list"))
    detail = api_client.get(reverse("v1:product-detail", args=[product.slug]))
    shades = api_client.get(reverse("v1:shade-list"))
    sizes = api_client.get(reverse("v1:size-list"))

    assert listing.data["count"] == 0
    assert detail.status_code == 404
    assert shades.data == []
    assert sizes.data == []


def test_deleting_a_brand_with_products_is_a_409_through_the_handler():
    brand = ProductFactory().brand

    with pytest.raises(ProtectedError) as exc_info:
        brand.delete()

    response = api_exception_handler(exc_info.value, {})
    assert response is not None
    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"


@pytest.mark.parametrize("brand_count", [2, 8])
def test_product_list_query_count_does_not_grow_with_brands(
    api_client, django_assert_num_queries, brand_count
):
    for _ in range(brand_count):
        ProductFactory(brand=BrandFactory(), is_published=True)

    with django_assert_num_queries(3):
        api_client.get(reverse("v1:product-list"))
