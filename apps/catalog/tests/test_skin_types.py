import pytest
from django.urls import reverse

from apps.catalog.tests.factories import (
    BrandFactory,
    CategoryFactory,
    ProductFactory,
    SkinTypeFactory,
)

pytestmark = pytest.mark.django_db


def _slugs(response):
    return sorted(result["slug"] for result in response.data["results"])


def test_skin_type_filter_returns_the_union_once_each(api_client):
    dry = SkinTypeFactory(slug="dry")
    oily = SkinTypeFactory(slug="oily")
    ProductFactory(slug="both", is_published=True).skin_types.set([dry, oily])
    ProductFactory(slug="dry-only", is_published=True).skin_types.set([dry])
    ProductFactory(slug="oily-only", is_published=True).skin_types.set([oily])
    ProductFactory(slug="sensitive-only", is_published=True).skin_types.set(
        [SkinTypeFactory(slug="sensitive")]
    )
    ProductFactory(slug="untyped", is_published=True)

    response = api_client.get(reverse("v1:product-list"), {"skin_type": ["dry", "oily"]})

    assert response.status_code == 200
    assert _slugs(response) == ["both", "dry-only", "oily-only"]


def test_an_unknown_skin_type_slug_is_a_400(api_client):
    response = api_client.get(reverse("v1:product-list"), {"skin_type": "scaly"})

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_a_parent_category_matches_its_childrens_products(api_client):
    skincare = CategoryFactory(slug="skincare")
    ProductFactory(slug="in-parent", is_published=True, category=skincare)
    ProductFactory(slug="in-child", is_published=True, category=CategoryFactory(parent=skincare))
    ProductFactory(slug="elsewhere", is_published=True)

    response = api_client.get(reverse("v1:product-list"), {"category": "skincare"})

    assert _slugs(response) == ["in-child", "in-parent"]


def test_a_child_category_does_not_match_its_siblings(api_client):
    skincare = CategoryFactory(slug="skincare")
    tone = CategoryFactory(slug="tone", parent=skincare)
    ProductFactory(slug="toner", is_published=True, category=tone)
    ProductFactory(slug="cleanser", is_published=True, category=CategoryFactory(parent=skincare))

    response = api_client.get(reverse("v1:product-list"), {"category": "tone"})

    assert _slugs(response) == ["toner"]


def test_the_facet_lists_skin_types_of_visible_products_in_sort_order(api_client):
    oily = SkinTypeFactory(name="Oily", slug="oily", sort_order=2)
    dry = SkinTypeFactory(name="Dry", slug="dry", sort_order=1)
    unpublished_only = SkinTypeFactory(slug="mature")
    inactive_brand_only = SkinTypeFactory(slug="sensitive")
    SkinTypeFactory(slug="unused")
    ProductFactory(is_published=True).skin_types.set([oily, dry])
    ProductFactory(is_published=True).skin_types.set([dry])
    ProductFactory(is_published=False).skin_types.set([unpublished_only])
    ProductFactory(is_published=True, brand=BrandFactory(is_active=False)).skin_types.set(
        [inactive_brand_only]
    )

    response = api_client.get(reverse("v1:skin-type-list"))

    assert response.status_code == 200
    assert response.data == [{"name": "Dry", "slug": "dry"}, {"name": "Oily", "slug": "oily"}]


def test_product_detail_carries_the_care_fields(api_client):
    product = ProductFactory(
        is_published=True,
        skin_feel="Soothed, balanced, refreshed",
        key_ingredients="Water (Aqua), Niacinamide",
    )
    product.skin_types.set(
        [
            SkinTypeFactory(name="Oily", slug="oily", sort_order=2),
            SkinTypeFactory(name="Combination", slug="combination", sort_order=1),
        ]
    )

    response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert response.data["skin_types"] == [
        {"name": "Combination", "slug": "combination"},
        {"name": "Oily", "slug": "oily"},
    ]
    assert response.data["skin_feel"] == "Soothed, balanced, refreshed"
    assert response.data["key_ingredients"] == "Water (Aqua), Niacinamide"


def test_unset_care_fields_are_empty(api_client):
    product = ProductFactory(is_published=True)

    response = api_client.get(reverse("v1:product-detail", args=[product.slug]))

    assert response.data["skin_types"] == []
    assert response.data["skin_feel"] == ""
    assert response.data["key_ingredients"] == ""


def test_the_list_does_not_carry_the_care_fields(api_client):
    ProductFactory(is_published=True)

    response = api_client.get(reverse("v1:product-list"))

    assert not {"skin_types", "skin_feel", "key_ingredients"} & set(response.data["results"][0])
