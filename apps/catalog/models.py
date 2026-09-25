from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class Size(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    # Sizes are ordered by the body, not by the alphabet: S must precede M, which
    # must precede L. Nothing derivable from the name gives that order.
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "size"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Color(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "color"
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
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_published = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

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
    color = models.ForeignKey(Color, on_delete=models.PROTECT, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    # IntegerField, not PositiveIntegerField: the latter emits its own unnamed
    # CHECK (>= 0), which would duplicate the named constraint below that ADR 0004
    # and the feature document both refer to by behaviour.
    stock_quantity = models.IntegerField(default=0)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "product_variant"
        # No default ordering: sorting by size__sort_order would join two tables on
        # every variant read, including every prefetch. The browsing feature orders
        # explicitly where it needs to.
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "color"],
                name="product_variant_unique_product_size_color",
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
        # Every price read goes through here. `price_override` is null for almost
        # every row, so reading the column directly yields None and silently
        # produces a zero or a crash at the call site.
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
            # Partial, so a product may hold many non-primary images but only ever
            # one primary. Promoting a new primary must clear the old one in the
            # same transaction or this raises IntegrityError, which the handler
            # turns into a 409.
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
