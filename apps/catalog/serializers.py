from rest_framework import serializers

from apps.catalog.models import Category, Color, Product, ProductImage, ProductVariant, Size


class SizeSerializer(serializers.ModelSerializer[Size]):
    class Meta:
        model = Size
        fields = ("name", "slug")


class ColorSerializer(serializers.ModelSerializer[Color]):
    class Meta:
        model = Color
        fields = ("name", "slug")


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
    color = ColorSerializer(read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        # `stock_quantity` is deliberately absent, here and everywhere else: exact
        # inventory is commercially sensitive and this endpoint is public.
        fields = ("id", "size", "color", "price", "in_stock")

    def get_in_stock(self, obj: ProductVariant) -> bool:
        return obj.stock_quantity > 0


class ProductListSerializer(serializers.ModelSerializer[Product]):
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
            "category",
            "primary_image",
            "in_stock",
        )

    def get_primary_image(self, obj: Product) -> dict[str, str] | None:
        # Reads the prefetched images rather than querying for the primary one.
        # A merchant who never ticked "primary" still gets a card image, which is
        # why this falls back to the first image by sort_order.
        images = list(obj.images.all())
        if not images:
            return None
        primary = next((image for image in images if image.is_primary), images[0])
        return ProductImageSerializer(primary).data


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = (*ProductListSerializer.Meta.fields, "description", "images", "variants")
