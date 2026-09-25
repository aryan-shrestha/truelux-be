import pytest
from django.db import IntegrityError
from django.urls import reverse

from apps.catalog.tests.factories import (
    ProductFactory,
    ProductVariantFactory,
    ShadeFactory,
    SizeFactory,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("hex_code", ["red", "#FFF", "#GGGGGG"])
def test_malformed_hex_code_violates_constraint(hex_code):
    with pytest.raises(IntegrityError):
        ShadeFactory(hex_code=hex_code)


def test_two_shadeless_variants_of_one_size_violate_the_unique_constraint():
    variant = ProductVariantFactory(shade=None)

    with pytest.raises(IntegrityError):
        ProductVariantFactory(product=variant.product, size=variant.size, shade=None)


def test_shade_filter_matches_and_excludes_shadeless_products(api_client):
    warm_beige = ShadeFactory(slug="warm-beige")
    foundation = ProductFactory(slug="silk-foundation", is_published=True)
    ProductVariantFactory(product=foundation, shade=warm_beige)
    ProductVariantFactory(product=foundation, shade=ShadeFactory(slug="honey"))
    serum = ProductFactory(slug="hydra-serum", is_published=True)
    ProductVariantFactory(product=serum, shade=None)

    response = api_client.get(reverse("v1:product-list"), {"shade": "warm-beige"})

    assert [result["slug"] for result in response.data["results"]] == ["silk-foundation"]


def test_variant_shade_is_an_object_or_null(api_client):
    product = ProductFactory(is_published=True)
    ProductVariantFactory(
        product=product,
        size=SizeFactory(sort_order=0),
        shade=ShadeFactory(name="Warm Beige", slug="warm-beige", hex_code="#D8A47F"),
    )
    ProductVariantFactory(product=product, size=SizeFactory(sort_order=1), shade=None)

    response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    shades = [variant["shade"] for variant in response.data["variants"]]
    assert shades == [{"name": "Warm Beige", "slug": "warm-beige", "hex_code": "#D8A47F"}, None]


def test_shades_and_sizes_list_only_values_used_by_visible_products(api_client):
    visible = ProductFactory(is_published=True)
    hidden = ProductFactory(is_published=False)
    ProductVariantFactory(
        product=visible,
        size=SizeFactory(name="50 ml", slug="50-ml", sort_order=2),
        shade=ShadeFactory(name="Honey", slug="honey", sort_order=2),
    )
    ProductVariantFactory(
        product=visible,
        size=SizeFactory(name="30 ml", slug="30-ml", sort_order=1),
        shade=ShadeFactory(name="Ivory", slug="ivory", hex_code="#EDCDB2", sort_order=1),
    )
    ProductVariantFactory(
        product=hidden, size=SizeFactory(slug="hidden-size"), shade=ShadeFactory()
    )
    SizeFactory(slug="unused")

    shades = api_client.get(reverse("v1:shade-list"))
    sizes = api_client.get(reverse("v1:size-list"))

    assert shades.data == [
        {"name": "Ivory", "slug": "ivory", "hex_code": "#EDCDB2"},
        {"name": "Honey", "slug": "honey", "hex_code": "#D8A47F"},
    ]
    assert sizes.data == [{"name": "30 ml", "slug": "30-ml"}, {"name": "50 ml", "slug": "50-ml"}]


def test_a_shade_used_twice_is_listed_once(api_client):
    shade = ShadeFactory()
    for _ in range(2):
        ProductVariantFactory(product=ProductFactory(is_published=True), shade=shade)

    response = api_client.get(reverse("v1:shade-list"))

    assert len(response.data) == 1
