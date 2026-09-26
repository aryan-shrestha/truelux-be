from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class Brand(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="brands/", blank=True)
    # Deactivating hides the brand and every product of it from the public API;
    # PROTECT on Product.brand means deletion is not an option once it has products.
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "brand"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Size(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    # Volumes are ordered by amount, not alphabetically: "15 ml" before "100 ml".
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "size"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Shade(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    hex_code = models.CharField(max_length=7)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "shade"
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hex_code__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="shade_hex_code_format",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class SkinType(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "skin_type"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Category(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "category"
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Product(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_published = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    skin_types = models.ManyToManyField(SkinType, blank=True, related_name="products")
    skin_feel = models.CharField(max_length=200, blank=True)
    key_ingredients = models.TextField(blank=True)

    class Meta:
        db_table = "product"
        ordering = ["sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["is_published", "-created_at"], name="product_published_crtd_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class ProductVariant(UUIDModel, TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.ForeignKey(Size, on_delete=models.PROTECT, related_name="variants")
    shade = models.ForeignKey(
        Shade, on_delete=models.PROTECT, null=True, blank=True, related_name="variants"
    )
    sku = models.CharField(max_length=64, unique=True)
    # IntegerField, not PositiveIntegerField: the latter emits its own unnamed
    # CHECK (>= 0), which would duplicate the named constraint below that ADR 0004
    # and the feature document both refer to by behaviour.
    stock_quantity = models.IntegerField(default=0)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "product_variant"
        # No default ordering: sorting by size__sort_order would join two tables on
        # every variant read, including every prefetch.
        constraints = [
            # NULLS NOT DISTINCT (PostgreSQL 15+) so a nullable shade cannot let a
            # product hold two shadeless variants of one size (ADR 0010).
            models.UniqueConstraint(
                fields=["product", "size", "shade"],
                name="product_variant_unique_product_size_shade",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0),
                name="product_variant_stock_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(price_override__isnull=True) | models.Q(price_override__gt=0),
                name="product_variant_price_override_positive",
            ),
        ]

    def __str__(self) -> str:
        return self.sku

    @property
    def price(self) -> Decimal:
        if self.price_override is not None:
            return self.price_override
        return self.product.base_price


class ProductImage(UUIDModel, TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "product_image"
        ordering = ["sort_order", "created_at"]
        constraints = [
            # Promoting a new primary must clear the old one in the same transaction.
            models.UniqueConstraint(
                fields=["product", "is_primary"],
                condition=models.Q(is_primary=True),
                name="product_image_one_primary_per_product",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "sort_order"], name="product_image_sort_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} image {self.sort_order}"
