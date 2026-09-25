from decimal import Decimal

import pytest
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.catalog.tests.factories import (
    ColorFactory,
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
    SizeFactory,
)


@pytest.mark.django_db
def test_duplicate_size_and_color_for_product_violates_constraint():
    variant = ProductVariantFactory()

    with pytest.raises(IntegrityError):
        ProductVariantFactory(
            product=variant.product,
            size=variant.size,
            color=variant.color,
        )


@pytest.mark.django_db
def test_same_size_and_color_on_another_product_is_allowed():
    variant = ProductVariantFactory()

    other = ProductVariantFactory(size=variant.size, color=variant.color)

    assert other.product != variant.product


@pytest.mark.django_db
def test_duplicate_sku_violates_constraint():
    ProductVariantFactory(sku="TAKEN-1")

    with pytest.raises(IntegrityError):
        ProductVariantFactory(sku="TAKEN-1")


@pytest.mark.django_db
def test_negative_stock_violates_constraint():
    variant = ProductVariantFactory(stock_quantity=1)

    with pytest.raises(IntegrityError):
        type(variant).objects.filter(pk=variant.pk).update(stock_quantity=-1)


@pytest.mark.django_db
def test_zero_price_override_violates_constraint():
    with pytest.raises(IntegrityError):
        ProductVariantFactory(price_override=Decimal("0.00"))


@pytest.mark.django_db
def test_second_primary_image_violates_constraint():
    image = ProductImageFactory(is_primary=True)

    with pytest.raises(IntegrityError):
        ProductImageFactory(product=image.product, is_primary=True)


@pytest.mark.django_db
def test_many_non_primary_images_are_allowed_for_one_product():
    product = ProductFactory()

    ProductImageFactory.create_batch(3, product=product, is_primary=False)

    assert product.images.count() == 3


@pytest.mark.django_db
def test_variant_price_falls_back_to_product_base_price():
    product = ProductFactory(base_price=Decimal("4500.00"))
    variant = ProductVariantFactory(product=product, price_override=None)

    assert variant.price == Decimal("4500.00")


@pytest.mark.django_db
def test_variant_price_override_wins_over_base_price():
    product = ProductFactory(base_price=Decimal("4500.00"))
    variant = ProductVariantFactory(product=product, price_override=Decimal("5200.00"))

    assert variant.price == Decimal("5200.00")


@pytest.mark.django_db
def test_deleting_a_size_in_use_is_protected():
    size = SizeFactory()
    ProductVariantFactory(size=size)

    with pytest.raises(ProtectedError):
        size.delete()


@pytest.mark.django_db
def test_deleting_an_unused_color_is_allowed():
    color = ColorFactory()

    color.delete()

    assert not type(color).objects.filter(pk=color.pk).exists()


@pytest.mark.django_db
def test_deleting_a_product_cascades_to_variants_and_images():
    variant = ProductVariantFactory()
    image = ProductImageFactory(product=variant.product)

    variant.product.delete()

    assert not type(variant).objects.filter(pk=variant.pk).exists()
    assert not type(image).objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_product_image_persists_a_storage_reference():
    image = ProductImageFactory()

    image.refresh_from_db()

    assert image.image.name.startswith("products/")
    assert default_storage.exists(image.image.name)
    assert image.image.url.endswith(image.image.name)
