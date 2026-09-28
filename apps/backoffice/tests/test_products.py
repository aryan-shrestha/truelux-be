from decimal import Decimal
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.backoffice.tests.conftest import image_upload
from apps.catalog.models import Product, ProductImage, ProductVariant
from apps.catalog.tests.factories import (
    BrandFactory,
    CategoryFactory,
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
    ShadeFactory,
    SizeFactory,
    SkinTypeFactory,
)
from apps.orders.tests.factories import OrderItemFactory

pytestmark = pytest.mark.django_db


def _product_payload(**overrides):
    payload = {
        "name": "Silk Foundation",
        "description": "Satin finish.",
        "brand_id": str(BrandFactory().pk),
        "category_id": str(CategoryFactory().pk),
        "base_price": "3200.00",
    }
    payload.update(overrides)
    return payload


def test_product_crud_round_trip(staff_client):
    created = staff_client.post(reverse("v1:admin-product-list"), _product_payload())
    product_id = created.data["id"]
    detail_url = reverse("v1:admin-product-detail", args=[product_id])

    patched = staff_client.patch(detail_url, {"base_price": "3500.00", "sort_order": 3})
    fetched = staff_client.get(detail_url)
    deleted = staff_client.delete(detail_url)

    assert created.status_code == 201
    assert created.data["slug"] == "silk-foundation"
    assert created.data["is_published"] is False
    assert created.data["variants"] == []
    assert patched.status_code == 200
    assert fetched.data["base_price"] == "3500.00"
    assert fetched.data["sort_order"] == 3
    assert deleted.status_code == 204
    assert not Product.objects.filter(pk=product_id).exists()


def test_product_write_sets_skin_types_and_care_fields(staff_client):
    dry = SkinTypeFactory(name="Dry", slug="dry", sort_order=1)
    oily = SkinTypeFactory(name="Oily", slug="oily", sort_order=2)

    created = staff_client.post(
        reverse("v1:admin-product-list"),
        _product_payload(
            skin_type_ids=[str(oily.pk), str(dry.pk)],
            skin_feel="Soothed, balanced, refreshed",
            key_ingredients="Water (Aqua), Niacinamide",
        ),
    )
    detail_url = reverse("v1:admin-product-detail", args=[created.data["id"]])
    renamed = staff_client.patch(detail_url, {"name": "Renamed"})
    replaced = staff_client.patch(detail_url, {"skin_type_ids": [str(oily.pk)]})
    cleared = staff_client.patch(detail_url, {"skin_type_ids": []})

    assert created.status_code == 201
    assert created.data["skin_types"] == [
        {"id": str(dry.pk), "name": "Dry", "slug": "dry"},
        {"id": str(oily.pk), "name": "Oily", "slug": "oily"},
    ]
    assert created.data["skin_feel"] == "Soothed, balanced, refreshed"
    assert created.data["key_ingredients"] == "Water (Aqua), Niacinamide"
    assert len(renamed.data["skin_types"]) == 2
    assert [skin_type["slug"] for skin_type in replaced.data["skin_types"]] == ["oily"]
    assert cleared.data["skin_types"] == []


def test_an_unknown_skin_type_id_is_a_400(staff_client):
    response = staff_client.post(
        reverse("v1:admin-product-list"),
        _product_payload(skin_type_ids=["00000000-0000-0000-0000-000000000000"]),
    )

    assert response.status_code == 400
    assert "skin_type_ids" in response.data["error"]["details"]
    assert not Product.objects.exists()


def test_a_derived_slug_is_made_unique(staff_client):
    ProductFactory(slug="silk-foundation")

    response = staff_client.post(reverse("v1:admin-product-list"), _product_payload())

    assert response.data["slug"] == "silk-foundation-2"


def test_a_duplicate_explicit_slug_is_a_409(staff_client):
    ProductFactory(slug="taken")

    response = staff_client.post(reverse("v1:admin-product-list"), _product_payload(slug="taken"))

    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"


def test_an_unknown_brand_is_a_400(staff_client):
    response = staff_client.post(
        reverse("v1:admin-product-list"),
        _product_payload(brand_id="00000000-0000-0000-0000-000000000000"),
    )

    assert response.status_code == 400
    assert "brand_id" in response.data["error"]["details"]


def test_creating_a_published_product_is_a_422(staff_client):
    response = staff_client.post(
        reverse("v1:admin-product-list"), _product_payload(is_published=True)
    )

    assert response.status_code == 422
    assert response.data["error"]["code"] == "product_has_no_variants"
    assert not Product.objects.exists()


def test_publishing_a_product_without_variants_is_a_422(staff_client):
    product = ProductFactory(is_published=False)

    response = staff_client.patch(
        reverse("v1:admin-product-detail", args=[product.pk]), {"is_published": True}
    )

    assert response.status_code == 422
    assert response.data["error"]["code"] == "product_has_no_variants"
    product.refresh_from_db()
    assert product.is_published is False


def test_publishing_a_product_with_a_variant_succeeds(staff_client):
    product = ProductVariantFactory(product__is_published=False).product

    response = staff_client.patch(
        reverse("v1:admin-product-detail", args=[product.pk]), {"is_published": True}
    )

    assert response.status_code == 200
    assert response.data["is_published"] is True


def test_deleting_an_ordered_product_is_a_409(staff_client):
    item = OrderItemFactory()

    response = staff_client.delete(
        reverse("v1:admin-product-detail", args=[item.variant.product_id])
    )

    assert response.status_code == 409
    assert Product.objects.filter(pk=item.variant.product_id).exists()


def test_product_list_includes_unpublished_and_inactive_brand_products(staff_client):
    ProductFactory(is_published=False)
    ProductFactory(brand=BrandFactory(is_active=False))

    response = staff_client.get(reverse("v1:admin-product-list"))

    assert response.data["count"] == 2


def test_product_list_item_shape(staff_client):
    product = ProductFactory()
    ProductVariantFactory(product=product, stock_quantity=4)
    ProductVariantFactory(product=product, stock_quantity=6)
    ProductImageFactory(product=product, is_primary=True)

    item = staff_client.get(reverse("v1:admin-product-list")).data["results"][0]

    assert item["variant_count"] == 2
    assert item["total_stock"] == 10
    assert item["primary_image_url"].startswith("/media/products/")
    assert "description" not in item
    assert "variants" not in item


def test_product_list_filters(staff_client):
    brand = BrandFactory()
    low = ProductFactory(brand=brand, name="Low")
    ProductVariantFactory(product=low, stock_quantity=2, sku="LUM-LOW-1")
    ProductVariantFactory(product=low, stock_quantity=1, sku="LUM-LOW-2")
    ProductVariantFactory(product=ProductFactory(name="Plenty"), stock_quantity=50)
    url = reverse("v1:admin-product-list")

    by_brand = staff_client.get(url, {"brand": str(brand.pk)})
    by_low_stock = staff_client.get(url, {"low_stock": "true"})
    by_sku = staff_client.get(url, {"search": "LUM-LOW"})
    ordered = staff_client.get(url, {"ordering": "-name"})

    assert [p["name"] for p in by_brand.data["results"]] == ["Low"]
    assert [p["name"] for p in by_low_stock.data["results"]] == ["Low"]
    assert [p["name"] for p in by_sku.data["results"]] == ["Low"]
    assert [p["name"] for p in ordered.data["results"]] == ["Plenty", "Low"]


@pytest.mark.parametrize("product_count", [2, 8])
def test_product_list_query_count_is_constant(
    staff_client, django_assert_num_queries, product_count
):
    for _ in range(product_count):
        product = ProductFactory()
        ProductVariantFactory(product=product)
        ProductImageFactory(product=product)

    with django_assert_num_queries(3):
        staff_client.get(reverse("v1:admin-product-list"))


def test_adding_a_variant(staff_client):
    product = ProductFactory()
    size = SizeFactory()
    shade = ShadeFactory(name="Warm Beige", hex_code="#D8A47F")

    response = staff_client.post(
        reverse("v1:admin-product-variants", args=[product.pk]),
        {
            "sku": "LUM-SF-30-WB",
            "size_id": str(size.pk),
            "shade_id": str(shade.pk),
            "stock_quantity": 12,
        },
    )

    assert response.status_code == 201
    assert response.data["shade"] == {
        "id": str(shade.pk),
        "name": "Warm Beige",
        "hex_code": "#D8A47F",
    }
    assert response.data["stock_quantity"] == 12
    assert response.data["price"] == "1000.00"


def test_a_duplicate_shadeless_variant_is_a_409(staff_client):
    variant = ProductVariantFactory(shade=None)

    response = staff_client.post(
        reverse("v1:admin-product-variants", args=[variant.product_id]),
        {"sku": "OTHER", "size_id": str(variant.size_id), "shade_id": None},
        format="json",
    )

    assert response.status_code == 409


def test_variant_stock_edit_goes_through_set_variant_stock(staff_client):
    variant = ProductVariantFactory(stock_quantity=3)

    with mock.patch(
        "apps.catalog.services.products.set_variant_stock", return_value=variant
    ) as set_stock:
        response = staff_client.patch(
            reverse("v1:admin-variant-detail", args=[variant.pk]),
            {"stock_quantity": 9, "price_override": "1200.00"},
        )

    assert response.status_code == 200
    set_stock.assert_called_once_with(variant=mock.ANY, quantity=9)
    variant.refresh_from_db()
    assert variant.price_override == Decimal("1200.00")


def test_negative_stock_is_a_400(staff_client):
    variant = ProductVariantFactory(stock_quantity=3)

    response = staff_client.patch(
        reverse("v1:admin-variant-detail", args=[variant.pk]), {"stock_quantity": -1}
    )

    assert response.status_code == 400
    variant.refresh_from_db()
    assert variant.stock_quantity == 3


def test_deleting_variants(staff_client):
    ordered = OrderItemFactory().variant
    unordered = ProductVariantFactory()

    blocked = staff_client.delete(reverse("v1:admin-variant-detail", args=[ordered.pk]))
    removed = staff_client.delete(reverse("v1:admin-variant-detail", args=[unordered.pk]))

    assert blocked.status_code == 409
    assert removed.status_code == 204
    assert not ProductVariant.objects.filter(pk=unordered.pk).exists()


def test_uploading_a_primary_image_demotes_the_old_one(staff_client):
    product = ProductFactory()
    old = ProductImageFactory(product=product, is_primary=True)

    response = staff_client.post(
        reverse("v1:admin-product-images", args=[product.pk]),
        {"image": image_upload(), "alt_text": "Front", "is_primary": True},
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["is_primary"] is True
    assert response.data["url"].endswith(".png")
    old.refresh_from_db()
    assert old.is_primary is False


def test_promoting_an_image_clears_the_old_primary(staff_client):
    product = ProductFactory()
    old = ProductImageFactory(product=product, is_primary=True)
    new = ProductImageFactory(product=product, is_primary=False)

    response = staff_client.patch(
        reverse("v1:admin-image-detail", args=[new.pk]), {"is_primary": True, "sort_order": 1}
    )

    assert response.status_code == 200
    old.refresh_from_db()
    new.refresh_from_db()
    assert (old.is_primary, new.is_primary, new.sort_order) == (False, True, 1)


def test_an_image_of_the_wrong_type_is_a_400(staff_client):
    product = ProductFactory()

    response = staff_client.post(
        reverse("v1:admin-product-images", args=[product.pk]),
        {"image": image_upload(image_format="GIF", name="photo.gif")},
        format="multipart",
    )

    assert response.status_code == 400
    assert "image" in response.data["error"]["details"]


def test_an_image_upload_that_is_not_multipart_is_a_415(staff_client):
    product = ProductFactory()

    response = staff_client.post(
        reverse("v1:admin-product-images", args=[product.pk]),
        "image=%89PNG&alt_text=Front",
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 415
    assert response.data["error"]["code"] == "unsupported_media_type"


def test_an_image_over_5_mb_is_a_400(staff_client):
    product = ProductFactory()
    upload = image_upload()
    oversized = SimpleUploadedFile(
        "big.png", upload.read() + b"\0" * (5 * 1024 * 1024), content_type="image/png"
    )

    response = staff_client.post(
        reverse("v1:admin-product-images", args=[product.pk]),
        {"image": oversized},
        format="multipart",
    )

    assert response.status_code == 400
    assert not ProductImage.objects.exists()


def test_deleting_an_image(staff_client):
    image = ProductImageFactory()

    response = staff_client.delete(reverse("v1:admin-image-detail", args=[image.pk]))

    assert response.status_code == 204
    assert not ProductImage.objects.exists()


def test_compare_at_price_round_trips_and_clears(staff_client):
    variant = ProductVariantFactory(product=ProductFactory(base_price=Decimal("2720.00")))
    url = reverse("v1:admin-variant-detail", args=[variant.pk])

    set_response = staff_client.patch(url, {"compare_at_price": "3200.00"}, format="json")
    detail = staff_client.get(reverse("v1:admin-product-detail", args=[variant.product_id]))
    cleared = staff_client.patch(url, {"compare_at_price": None}, format="json")

    assert set_response.status_code == 200
    assert set_response.data["compare_at_price"] == "3200.00"
    assert detail.data["variants"][0]["compare_at_price"] == "3200.00"
    assert cleared.data["compare_at_price"] is None


def test_adding_a_variant_on_sale(staff_client):
    product = ProductFactory(base_price=Decimal("3200.00"))

    response = staff_client.post(
        reverse("v1:admin-product-variants", args=[product.pk]),
        {
            "sku": "SALE-1",
            "size_id": str(SizeFactory().pk),
            "price_override": "2720.00",
            "compare_at_price": "3200.00",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["compare_at_price"] == "3200.00"


@pytest.mark.parametrize("compare_at", ["2720.00", "2000.00", "0"])
def test_a_compare_at_not_above_the_price_is_a_400(staff_client, compare_at):
    variant = ProductVariantFactory(product=ProductFactory(base_price=Decimal("2720.00")))

    response = staff_client.patch(
        reverse("v1:admin-variant-detail", args=[variant.pk]),
        {"compare_at_price": compare_at},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert "compare_at_price" in response.data["error"]["details"]
    variant.refresh_from_db()
    assert variant.compare_at_price is None


def test_product_list_flags_and_filters_products_on_sale(staff_client):
    on_sale = ProductFactory(name="Sale", base_price=Decimal("2720.00"))
    ProductVariantFactory(product=on_sale, compare_at_price=Decimal("3200.00"))
    full_price = ProductFactory(name="Full", base_price=Decimal("3200.00"))
    ProductVariantFactory(product=full_price, compare_at_price=Decimal("3200.00"))
    url = reverse("v1:admin-product-list")

    listed = {p["name"]: p["on_sale"] for p in staff_client.get(url).data["results"]}
    filtered = staff_client.get(url, {"on_sale": "true"})
    invalid = staff_client.get(url, {"on_sale": "yes"})

    assert listed == {"Sale": True, "Full": False}
    assert [p["name"] for p in filtered.data["results"]] == ["Sale"]
    assert invalid.status_code == 400
