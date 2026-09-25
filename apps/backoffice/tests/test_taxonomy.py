import pytest
from django.urls import reverse

from apps.backoffice.tests.conftest import image_upload
from apps.catalog.models import Brand, Shade, Size
from apps.catalog.tests.factories import (
    BrandFactory,
    CategoryFactory,
    ProductFactory,
    ProductVariantFactory,
    ShadeFactory,
    SizeFactory,
)

pytestmark = pytest.mark.django_db


def test_brand_list_includes_inactive_brands_with_counts(staff_client):
    active = BrandFactory(name="Aurum", sort_order=0)
    BrandFactory(name="Retired", is_active=False, sort_order=1)
    ProductFactory.create_batch(2, brand=active, is_published=False)

    response = staff_client.get(reverse("v1:admin-brand-list"))

    assert response.status_code == 200
    assert [brand["name"] for brand in response.data] == ["Aurum", "Retired"]
    assert response.data[0]["product_count"] == 2
    assert {"id", "is_active", "logo_url"} <= set(response.data[0])


def test_brand_create_with_a_logo_derives_the_slug(staff_client):
    response = staff_client.post(
        reverse("v1:admin-brand-list"),
        {"name": "Lumière", "logo": image_upload(name="logo.png")},
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["slug"] == "lumiere"
    assert response.data["logo_url"].startswith("/media/brands/")
    assert response.data["product_count"] == 0


def test_brand_update_and_deactivate(staff_client):
    brand = BrandFactory()

    response = staff_client.patch(
        reverse("v1:admin-brand-detail", args=[brand.pk]),
        {"is_active": False, "description": "Paused."},
    )

    assert response.status_code == 200
    brand.refresh_from_db()
    assert (brand.is_active, brand.description) == (False, "Paused.")


def test_deleting_a_brand_with_products_is_a_409(staff_client):
    brand = ProductFactory().brand

    response = staff_client.delete(reverse("v1:admin-brand-detail", args=[brand.pk]))

    assert response.status_code == 409
    assert Brand.objects.filter(pk=brand.pk).exists()


def test_deleting_an_unused_brand(staff_client):
    brand = BrandFactory()

    response = staff_client.delete(reverse("v1:admin-brand-detail", args=[brand.pk]))

    assert response.status_code == 204


def test_shade_crud_and_validation(staff_client):
    created = staff_client.post(
        reverse("v1:admin-shade-list"), {"name": "Warm Beige", "hex_code": "#D8A47F"}
    )
    invalid = staff_client.post(reverse("v1:admin-shade-list"), {"name": "Red", "hex_code": "red"})
    listed = staff_client.get(reverse("v1:admin-shade-list"))

    assert created.status_code == 201
    assert created.data["slug"] == "warm-beige"
    assert created.data["variant_count"] == 0
    assert invalid.status_code == 400
    assert [shade["name"] for shade in listed.data] == ["Warm Beige"]


def test_deleting_a_referenced_shade_or_size_is_a_409(staff_client):
    variant = ProductVariantFactory(shade=ShadeFactory())

    shade = staff_client.delete(reverse("v1:admin-shade-detail", args=[variant.shade_id]))
    size = staff_client.delete(reverse("v1:admin-size-detail", args=[variant.size_id]))

    assert (shade.status_code, size.status_code) == (409, 409)
    assert Shade.objects.filter(pk=variant.shade_id).exists()
    assert Size.objects.filter(pk=variant.size_id).exists()


def test_size_list_counts_variants(staff_client):
    size = SizeFactory(name="50 ml")
    for _ in range(2):
        ProductVariantFactory(size=size)

    response = staff_client.get(reverse("v1:admin-size-list"))

    assert response.data == [
        {
            "id": str(size.pk),
            "name": "50 ml",
            "slug": size.slug,
            "sort_order": 0,
            "variant_count": 2,
        }
    ]


def test_a_duplicate_name_is_a_409(staff_client):
    SizeFactory(name="50 ml", slug="fifty")

    response = staff_client.post(reverse("v1:admin-size-list"), {"name": "50 ml"})

    assert response.status_code == 409


def test_category_create_with_a_parent(staff_client):
    parent = CategoryFactory()

    response = staff_client.post(
        reverse("v1:admin-category-list"), {"name": "Serums", "parent_id": str(parent.pk)}
    )

    assert response.status_code == 201
    assert response.data["parent_id"] == str(parent.pk)


@pytest.mark.parametrize("depth", [0, 2])
def test_a_category_cannot_become_its_own_ancestor(staff_client, depth):
    root = CategoryFactory()
    descendant = root
    for _ in range(depth):
        descendant = CategoryFactory(parent=descendant)

    response = staff_client.patch(
        reverse("v1:admin-category-detail", args=[root.pk]), {"parent_id": str(descendant.pk)}
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert "parent_id" in response.data["error"]["details"]


def test_deleting_a_category_with_products_is_a_409(staff_client):
    category = ProductFactory().category

    response = staff_client.delete(reverse("v1:admin-category-detail", args=[category.pk]))

    assert response.status_code == 409
