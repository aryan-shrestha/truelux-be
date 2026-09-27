from decimal import Decimal
from typing import Any

from django.core.files import File
from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.catalog.constants import ALLOWED_IMAGE_FORMATS, MAX_IMAGE_BYTES
from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Shade,
    Size,
    SkinType,
)
from apps.orders.constants import ALLOWED_TRANSITIONS, OrderStatus
from apps.orders.models import Order, OrderItem, ShippingSettings


def validate_image_upload(upload: "File[Any]") -> None:
    if (upload.size or 0) > MAX_IMAGE_BYTES:
        raise serializers.ValidationError("Images must be 5 MB or smaller.")
    # DRF's ImageField has already opened the file with Pillow and attached it.
    image_format = getattr(getattr(upload, "image", None), "format", None)
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise serializers.ValidationError("Images must be JPEG, PNG or WebP.")


class BrandRefSerializer(serializers.ModelSerializer[Brand]):
    class Meta:
        model = Brand
        fields = ("id", "name", "slug")


class CategoryRefSerializer(serializers.ModelSerializer[Category]):
    class Meta:
        model = Category
        fields = ("id", "name", "slug")


class SizeRefSerializer(serializers.ModelSerializer[Size]):
    class Meta:
        model = Size
        fields = ("id", "name")


class ShadeRefSerializer(serializers.ModelSerializer[Shade]):
    class Meta:
        model = Shade
        fields = ("id", "name", "hex_code")


class SkinTypeRefSerializer(serializers.ModelSerializer[SkinType]):
    class Meta:
        model = SkinType
        fields = ("id", "name", "slug")


class AdminVariantSerializer(serializers.ModelSerializer[ProductVariant]):
    size = SizeRefSerializer(read_only=True)
    shade = ShadeRefSerializer(read_only=True, allow_null=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ("id", "sku", "size", "shade", "stock_quantity", "price_override", "price")


class AdminImageSerializer(serializers.ModelSerializer[ProductImage]):
    url = serializers.CharField(source="image.url", read_only=True)

    class Meta:
        model = ProductImage
        fields = ("id", "url", "alt_text", "sort_order", "is_primary")


class AdminProductListSerializer(serializers.ModelSerializer[Product]):
    brand = BrandRefSerializer(read_only=True)
    category = CategoryRefSerializer(read_only=True)
    variant_count = serializers.IntegerField(read_only=True)
    total_stock = serializers.IntegerField(read_only=True)
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "brand",
            "category",
            "base_price",
            "is_published",
            "sort_order",
            "variant_count",
            "total_stock",
            "primary_image_url",
            "created_at",
            "updated_at",
        )

    def get_primary_image_url(self, obj: Product) -> str | None:
        images = list(obj.images.all())
        if not images:
            return None
        primary = next((image for image in images if image.is_primary), images[0])
        return str(primary.image.url)


class AdminProductDetailSerializer(serializers.ModelSerializer[Product]):
    brand = BrandRefSerializer(read_only=True)
    category = CategoryRefSerializer(read_only=True)
    skin_types = SkinTypeRefSerializer(many=True, read_only=True)
    variants = AdminVariantSerializer(many=True, read_only=True)
    images = AdminImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "brand",
            "category",
            "base_price",
            "is_published",
            "sort_order",
            "skin_types",
            "skin_feel",
            "key_ingredients",
            "variants",
            "images",
            "created_at",
            "updated_at",
        )


class ProductWriteSerializer(serializers.Serializer[Product]):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    brand_id = serializers.PrimaryKeyRelatedField(queryset=Brand.objects.all(), source="brand")
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category"
    )
    base_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.00")
    )
    is_published = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(min_value=0, required=False)
    skin_type_ids = serializers.PrimaryKeyRelatedField(
        queryset=SkinType.objects.all(), source="skin_types", many=True, required=False
    )
    skin_feel = serializers.CharField(max_length=200, required=False, allow_blank=True)
    key_ingredients = serializers.CharField(required=False, allow_blank=True)


class VariantWriteSerializer(serializers.Serializer[ProductVariant]):
    sku = serializers.CharField(max_length=64)
    size_id = serializers.PrimaryKeyRelatedField(queryset=Size.objects.all(), source="size")
    shade_id = serializers.PrimaryKeyRelatedField(
        queryset=Shade.objects.all(), source="shade", allow_null=True, required=False
    )
    stock_quantity = serializers.IntegerField(min_value=0, required=False)
    price_override = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        allow_null=True,
        required=False,
    )


class ImageCreateSerializer(serializers.Serializer[ProductImage]):
    image = serializers.ImageField(validators=[validate_image_upload])
    alt_text = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False, default=False)


class ImageUpdateSerializer(serializers.Serializer[ProductImage]):
    alt_text = serializers.CharField(max_length=255, required=False, allow_blank=True)
    sort_order = serializers.IntegerField(min_value=0, required=False)
    is_primary = serializers.BooleanField(required=False)


class AdminBrandSerializer(serializers.ModelSerializer[Brand]):
    logo_url = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Brand
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "logo_url",
            "is_active",
            "sort_order",
            "product_count",
        )

    def get_logo_url(self, obj: Brand) -> str | None:
        return obj.logo.url if obj.logo else None


class BrandWriteSerializer(serializers.Serializer[Brand]):
    name = serializers.CharField(max_length=150)
    slug = serializers.SlugField(max_length=150, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    logo = serializers.ImageField(required=False, validators=[validate_image_upload])
    is_active = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(min_value=0, required=False)


class AdminCategorySerializer(serializers.ModelSerializer[Category]):
    parent_id = serializers.UUIDField(read_only=True, allow_null=True)
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent_id", "sort_order", "product_count")


class CategoryWriteSerializer(serializers.Serializer[Category]):
    name = serializers.CharField(max_length=150)
    slug = serializers.SlugField(max_length=150, required=False, allow_blank=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="parent", allow_null=True, required=False
    )
    sort_order = serializers.IntegerField(min_value=0, required=False)


class AdminShadeSerializer(serializers.ModelSerializer[Shade]):
    variant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Shade
        fields = ("id", "name", "slug", "hex_code", "sort_order", "variant_count")


class ShadeWriteSerializer(serializers.Serializer[Shade]):
    name = serializers.CharField(max_length=50)
    slug = serializers.SlugField(max_length=50, required=False, allow_blank=True)
    hex_code = serializers.CharField(
        max_length=7,
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use the #RRGGBB form.")],
    )
    sort_order = serializers.IntegerField(min_value=0, required=False)


class AdminSizeSerializer(serializers.ModelSerializer[Size]):
    variant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Size
        fields = ("id", "name", "slug", "sort_order", "variant_count")


class SizeWriteSerializer(serializers.Serializer[Size]):
    name = serializers.CharField(max_length=50)
    slug = serializers.SlugField(max_length=50, required=False, allow_blank=True)
    sort_order = serializers.IntegerField(min_value=0, required=False)


class AdminSkinTypeSerializer(serializers.ModelSerializer[SkinType]):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SkinType
        fields = ("id", "name", "slug", "sort_order", "product_count")


class SkinTypeWriteSerializer(serializers.Serializer[SkinType]):
    name = serializers.CharField(max_length=50)
    slug = serializers.SlugField(max_length=50, required=False, allow_blank=True)
    sort_order = serializers.IntegerField(min_value=0, required=False)


class AdminOrderListSerializer(serializers.ModelSerializer[Order]):
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "status",
            "full_name",
            "phone",
            "total",
            "item_count",
            "created_at",
        )


class AdminOrderItemSerializer(serializers.ModelSerializer[OrderItem]):
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "product_name",
            "sku",
            "variant_size",
            "variant_shade",
            "quantity",
            "unit_price",
            "line_total",
        )

    def get_line_total(self, obj: OrderItem) -> str:
        return f"{obj.unit_price * obj.quantity:.2f}"


class AdminOrderDetailSerializer(serializers.ModelSerializer[Order]):
    item_count = serializers.SerializerMethodField()
    allowed_transitions = serializers.SerializerMethodField()
    items = AdminOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            *AdminOrderListSerializer.Meta.fields,
            "email",
            "address_line",
            "city",
            "district",
            "note",
            "subtotal",
            "shipping_fee",
            "payment_method",
            "allowed_transitions",
            "items",
        )

    def get_item_count(self, obj: Order) -> int:
        return sum(item.quantity for item in obj.items.all())

    def get_allowed_transitions(self, obj: Order) -> list[str]:
        return list(ALLOWED_TRANSITIONS[obj.status])


class TransitionSerializer(serializers.Serializer[Order]):
    to = serializers.ChoiceField(
        choices=[
            OrderStatus.CONFIRMED,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
        ]
    )


class LowStockSerializer(serializers.ModelSerializer[ProductVariant]):
    variant_id = serializers.UUIDField(source="id")
    product_name = serializers.CharField(source="product.name")
    size = serializers.CharField(source="size.name")
    shade = serializers.CharField(source="shade.name", allow_null=True, default=None)

    class Meta:
        model = ProductVariant
        fields = (
            "variant_id",
            "product_id",
            "product_name",
            "sku",
            "size",
            "shade",
            "stock_quantity",
        )


class SalesDaySerializer(serializers.Serializer[dict[str, Any]]):
    date = serializers.DateField()
    orders = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)


class RevenueSerializer(serializers.Serializer[dict[str, Any]]):
    today = serializers.DecimalField(max_digits=12, decimal_places=2)
    last_7_days = serializers.DecimalField(max_digits=12, decimal_places=2)
    last_30_days = serializers.DecimalField(max_digits=12, decimal_places=2)


class DashboardSerializer(serializers.Serializer[dict[str, Any]]):
    orders_by_status = serializers.DictField(child=serializers.IntegerField())
    revenue = RevenueSerializer()
    sales_by_day = SalesDaySerializer(many=True)
    recent_orders = AdminOrderListSerializer(many=True)
    low_stock = LowStockSerializer(many=True)


class AdminShippingSettingsSerializer(serializers.ModelSerializer[ShippingSettings]):
    class Meta:
        model = ShippingSettings
        fields = (
            "inside_valley_fee",
            "outside_valley_fee",
            "free_shipping_threshold",
            "updated_at",
        )


class ShippingSettingsWriteSerializer(serializers.Serializer[ShippingSettings]):
    inside_valley_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.00")
    )
    outside_valley_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.00")
    )
    free_shipping_threshold = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"), allow_null=True
    )
