from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

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


class SizeFactory(DjangoModelFactory[Size]):
    class Meta:
        model = Size

    name = factory.Sequence(lambda n: f"Size {n}")
    slug = factory.Sequence(lambda n: f"size-{n}")


class BrandFactory(DjangoModelFactory[Brand]):
    class Meta:
        model = Brand

    name = factory.Sequence(lambda n: f"Brand {n}")
    slug = factory.Sequence(lambda n: f"brand-{n}")


class ShadeFactory(DjangoModelFactory[Shade]):
    class Meta:
        model = Shade

    name = factory.Sequence(lambda n: f"Shade {n}")
    slug = factory.Sequence(lambda n: f"shade-{n}")
    hex_code = "#D8A47F"


class SkinTypeFactory(DjangoModelFactory[SkinType]):
    class Meta:
        model = SkinType

    name = factory.Sequence(lambda n: f"Skin type {n}")
    slug = factory.Sequence(lambda n: f"skin-type-{n}")


class CategoryFactory(DjangoModelFactory[Category]):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")


class ProductFactory(DjangoModelFactory[Product]):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Product {n}")
    slug = factory.Sequence(lambda n: f"product-{n}")
    brand = factory.SubFactory(BrandFactory)
    category = factory.SubFactory(CategoryFactory)
    base_price = Decimal("1000.00")


class ProductVariantFactory(DjangoModelFactory[ProductVariant]):
    class Meta:
        model = ProductVariant

    product = factory.SubFactory(ProductFactory)
    size = factory.SubFactory(SizeFactory)
    sku = factory.Sequence(lambda n: f"SKU-{n}")


class ProductImageFactory(DjangoModelFactory[ProductImage]):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = factory.django.ImageField(filename="product.jpg")
