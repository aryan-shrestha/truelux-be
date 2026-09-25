from collections.abc import Mapping
from typing import Any

from django.core.files import File
from django.db import transaction

from apps.catalog.exceptions import ProductHasNoVariants
from apps.catalog.models import Product, ProductImage, ProductVariant
from apps.catalog.services._slugs import unique_slug
from apps.catalog.services.stock import set_variant_stock
from apps.core.logging import get_logger

logger = get_logger(__name__)

PRODUCT_FIELDS = frozenset(
    {"name", "slug", "description", "brand", "category", "base_price", "sort_order"}
)
VARIANT_FIELDS = frozenset({"sku", "size", "shade", "price_override"})
IMAGE_FIELDS = frozenset({"alt_text", "sort_order"})


def _assign(instance: Any, fields: Mapping[str, Any], allowed: frozenset[str]) -> None:
    for name, value in fields.items():
        if name not in allowed:
            raise ValueError(f"{type(instance).__name__}.{name} is not writable here.")
        setattr(instance, name, value)


def _ensure_publishable(product: Product) -> None:
    if not product.variants.exists():
        raise ProductHasNoVariants(details={"product_id": str(product.pk)})


def create_product(*, fields: Mapping[str, Any], is_published: bool = False) -> Product:
    """Raises ProductHasNoVariants when asked to publish: a new product has none yet."""
    if is_published:
        raise ProductHasNoVariants()

    product = Product()
    _assign(product, fields, PRODUCT_FIELDS)
    if not product.slug:
        product.slug = unique_slug(model=Product, name=product.name, max_length=200)
    product.save()

    logger.info("catalog.product_created", product_id=str(product.pk))
    return product


def update_product(
    *, product: Product, fields: Mapping[str, Any], is_published: bool | None = None
) -> Product:
    """Raises ProductHasNoVariants when publishing a product that has no variants."""
    _assign(product, fields, PRODUCT_FIELDS)
    if "slug" in fields and not product.slug:
        product.slug = unique_slug(model=Product, name=product.name, max_length=200)
    if is_published is not None:
        if is_published:
            _ensure_publishable(product)
        product.is_published = is_published
    product.save()

    logger.info("catalog.product_updated", product_id=str(product.pk))
    return product


def set_product_published(*, product: Product, is_published: bool) -> Product:
    """Raises ProductHasNoVariants when publishing a product that has no variants."""
    return update_product(product=product, fields={}, is_published=is_published)


def delete_product(*, product: Product) -> None:
    """Raises ProtectedError (a 409) once any of its variants has been ordered."""
    product_id = str(product.pk)
    product.delete()
    logger.info("catalog.product_deleted", product_id=product_id)


def create_variant(
    *, product: Product, fields: Mapping[str, Any], stock_quantity: int = 0
) -> ProductVariant:
    variant = ProductVariant(product=product, stock_quantity=stock_quantity)
    _assign(variant, fields, VARIANT_FIELDS)
    variant.save()

    logger.info("catalog.variant_created", variant_id=str(variant.pk), sku=variant.sku)
    return variant


def update_variant(
    *, variant: ProductVariant, fields: Mapping[str, Any], stock_quantity: int | None = None
) -> ProductVariant:
    """Stock goes through set_variant_stock, so it takes the row lock."""
    if fields:
        _assign(variant, fields, VARIANT_FIELDS)
        variant.save(update_fields=[*fields, "updated_at"])
    if stock_quantity is not None:
        variant = set_variant_stock(variant=variant, quantity=stock_quantity)
    return variant


def delete_variant(*, variant: ProductVariant) -> None:
    """Raises ProtectedError (a 409) once the variant has been ordered."""
    variant_id = str(variant.pk)
    variant.delete()
    logger.info("catalog.variant_deleted", variant_id=variant_id)


def _clear_primary(product_id: Any, *, keep: ProductImage) -> None:
    ProductImage.objects.filter(product_id=product_id, is_primary=True).exclude(pk=keep.pk).update(
        is_primary=False
    )


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
            _clear_primary(product.pk, keep=product_image)
        product_image.save()

    logger.info("catalog.image_added", image_id=str(product_image.pk))
    return product_image


def update_product_image(
    *, image: ProductImage, fields: Mapping[str, Any], is_primary: bool | None = None
) -> ProductImage:
    """Promoting an image to primary clears the old primary in the same transaction,
    which the one-primary-per-product constraint requires."""
    _assign(image, fields, IMAGE_FIELDS)
    with transaction.atomic():
        if is_primary:
            _clear_primary(image.product_id, keep=image)
        if is_primary is not None:
            image.is_primary = is_primary
        image.save()
    return image


def delete_product_image(*, image: ProductImage) -> None:
    """Deletes the row only; the stored asset is left behind (architecture.md)."""
    image_id = str(image.pk)
    image.delete()
    logger.info("catalog.image_deleted", image_id=image_id)
