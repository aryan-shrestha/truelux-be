from rest_framework import serializers

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


class SizeSerializer(serializers.ModelSerializer[Size]):
    class Meta:
        model = Size
        fields = ("name", "slug")


class ShadeSerializer(serializers.ModelSerializer[Shade]):
    class Meta:
        model = Shade
        fields = ("name", "slug", "hex_code")


class SkinTypeSerializer(serializers.ModelSerializer[SkinType]):
    class Meta:
        model = SkinType
        fields = ("name", "slug")


class BrandSummarySerializer(serializers.ModelSerializer[Brand]):
    class Meta:
        model = Brand
        fields = ("name", "slug")


class BrandSerializer(serializers.ModelSerializer[Brand]):
    logo_url = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Brand
        fields = ("name", "slug", "description", "logo_url", "product_count")

    def get_logo_url(self, obj: Brand) -> str | None:
        return obj.logo.url if obj.logo else None


class CategorySerializer(serializers.ModelSerializer[Category]):
    class Meta:
        model = Category
        fields = ("name", "slug")


class CategoryTreeSerializer(serializers.ModelSerializer[Category]):
    children = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ("name", "slug", "children")


class ProductImageSerializer(serializers.ModelSerializer[ProductImage]):
    url = serializers.CharField(source="image.url", read_only=True)

    class Meta:
        model = ProductImage
        fields = ("url", "alt_text")


class ProductVariantSerializer(serializers.ModelSerializer[ProductVariant]):
    size = SizeSerializer(read_only=True)
    shade = ShadeSerializer(read_only=True, allow_null=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        # No `stock_quantity`: exact inventory is commercially sensitive and this is public.
        fields = ("id", "size", "shade", "price", "in_stock")

    def get_in_stock(self, obj: ProductVariant) -> bool:
        return obj.stock_quantity > 0


class ProductListSerializer(serializers.ModelSerializer[Product]):
    brand = BrandSummarySerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        # Annotated so ProductDetailSerializer.Meta can extend it.
        fields: tuple[str, ...] = (
            "id",
            "name",
            "slug",
            "base_price",
            "brand",
            "category",
            "primary_image",
            "in_stock",
        )

    def get_primary_image(self, obj: Product) -> dict[str, str] | None:
        # Reads the prefetch; falls back to the first image when none is primary.
        images = list(obj.images.all())
        if not images:
            return None
        primary = next((image for image in images if image.is_primary), images[0])
        return ProductImageSerializer(primary).data


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    skin_types = SkinTypeSerializer(many=True, read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = (
            *ProductListSerializer.Meta.fields,
            "description",
            "images",
            "variants",
            "skin_types",
            "skin_feel",
            "key_ingredients",
        )
