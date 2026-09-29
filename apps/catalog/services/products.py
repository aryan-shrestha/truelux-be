from collections.abc import Iterable, Mapping
from typing import Any

from django.core.files import File
from django.db import transaction

from apps.catalog.exceptions import CompareAtNotAbovePrice, ProductHasNoVariants
from apps.catalog.models import Product, ProductImage, ProductVariant, SkinType
from apps.catalog.services._writes import assign_fields, fill_missing_slug
from apps.catalog.services.stock import set_variant_stock
from apps.core.logging import get_logger

logger = get_logger(__name__)

PRODUCT_FIELDS = frozenset(
    {
        "name",
        "slug",
        "description",
        "brand",
        "category",
        "base_price",
        "sort_order",
        "skin_feel",
        "key_ingredients",
    }
)
VARIANT_FIELDS = frozenset({"sku", "size", "shade", "price_override", "compare_at_price"})
IMAGE_FIELDS = frozenset({"alt_text", "sort_order"})


def _ensure_publishable(product: Product) -> None:
    if not product.variants.exists():
        raise ProductHasNoVariants(details={"product_id": str(product.pk)})


def create_product(
    *,
    fields: Mapping[str, Any],
    is_published: bool = False,
    skin_types: Iterable[SkinType] | None = None,
) -> Product:
    """Raises ProductHasNoVariants when asked to publish: a new product has none yet."""
    if is_published:
        raise ProductHasNoVariants()

    product = Product()
    assign_fields(product, fields, PRODUCT_FIELDS)
    fill_missing_slug(product)
    with transaction.atomic():
        product.save()
        if skin_types is not None:
            product.skin_types.set(skin_types)

    logger.info("catalog.product_created", product_id=str(product.pk))
    return product


def update_product(
    *,
    product: Product,
    fields: Mapping[str, Any],
    is_published: bool | None = None,
    skin_types: Iterable[SkinType] | None = None,
) -> Product:
    """Raises ProductHasNoVariants when publishing a product that has no variants."""
    assign_fields(product, fields, PRODUCT_FIELDS)
    fill_missing_slug(product)
    if is_published is not None:
        if is_published:
            _ensure_publishable(product)
        product.is_published = is_published
    with transaction.atomic():
        product.save()
        if skin_types is not None:
            product.skin_types.set(skin_types)

    logger.info("catalog.product_updated", product_id=str(product.pk))
    return product


def delete_product(*, product: Product) -> None:
    """Raises ProtectedError (a 409) once any of its variants has been ordered."""
    product_id = str(product.pk)
    product.delete()
    logger.info("catalog.product_deleted", product_id=product_id)


def _ensure_compare_at_above_price(variant: ProductVariant) -> None:
    if variant.compare_at_price is not None and variant.compare_at_price <= variant.price:
        raise CompareAtNotAbovePrice()


def create_variant(
    *, product: Product, fields: Mapping[str, Any], stock_quantity: int = 0
) -> ProductVariant:
    """Raises CompareAtNotAbovePrice for a compare-at at or below the resolved price."""
    variant = ProductVariant(product=product, stock_quantity=stock_quantity)
    assign_fields(variant, fields, VARIANT_FIELDS)
    _ensure_compare_at_above_price(variant)
    variant.save()

    logger.info("catalog.variant_created", variant_id=str(variant.pk), sku=variant.sku)
    return variant


def update_variant(
    *, variant: ProductVariant, fields: Mapping[str, Any], stock_quantity: int | None = None
) -> ProductVariant:
    """Stock goes through set_variant_stock, so it takes the row lock.

    A compare-at is checked against the price only when it is written: repricing
    past an existing compare-at is allowed and simply ends the sale (ADR 0018).
    """
    if fields:
        assign_fields(variant, fields, VARIANT_FIELDS)
        if "compare_at_price" in fields:
            _ensure_compare_at_above_price(variant)
        variant.save(update_fields=[*fields, "updated_at"])
    if stock_quantity is not None:
        variant = set_variant_stock(variant=variant, quantity=stock_quantity)
    return variant


def delete_variant(*, variant: ProductVariant) -> None:
    """Raises ProtectedError (a 409) once the variant has been ordered."""
    variant_id = str(variant.pk)
    variant.delete()
    logger.info("catalog.variant_deleted", variant_id=variant_id)


def _demote_other_primaries(image: ProductImage) -> None:
    ProductImage.objects.filter(product_id=image.product_id, is_primary=True).exclude(
        pk=image.pk
    ).update(is_primary=False)


def add_product_image(
    *,
    product: Product,
    image: File,  # type: ignore[type-arg]  # File is not subscriptable at runtime
    alt_text: str = "",
    is_primary: bool = False,
) -> ProductImage:
    product_image = ProductImage(product=product, alt_text=alt_text, is_primary=is_primary)
    # Uploaded to storage (Cloudinary in production) before any transaction opens:
    # an upload of unbounded duration must not hold a pooled connection.
    product_image.image.save(image.name or "upload", image, save=False)

    with transaction.atomic():
        if is_primary:
            _demote_other_primaries(product_image)
        product_image.save()

    logger.info("catalog.image_added", image_id=str(product_image.pk))
    return product_image


def update_product_image(
    *, image: ProductImage, fields: Mapping[str, Any], is_primary: bool | None = None
) -> ProductImage:
    """Promoting an image to primary clears the old primary in the same transaction,
    which the one-primary-per-product constraint requires."""
    assign_fields(image, fields, IMAGE_FIELDS)
    with transaction.atomic():
        if is_primary:
            _demote_other_primaries(image)
        if is_primary is not None:
            image.is_primary = is_primary
        image.save()
    return image


def delete_product_image(*, image: ProductImage) -> None:
    """Deletes the row only; the stored asset is left behind (architecture.md)."""
    image_id = str(image.pk)
    image.delete()
    logger.info("catalog.image_deleted", image_id=image_id)
