from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.catalog.models import Category, Color, Product, ProductImage, ProductVariant, Size


class SizeFactory(DjangoModelFactory[Size]):
    class Meta:
        model = Size

    name = factory.Sequence(lambda n: f"Size {n}")
    slug = factory.Sequence(lambda n: f"size-{n}")


class ColorFactory(DjangoModelFactory[Color]):
    class Meta:
        model = Color

    name = factory.Sequence(lambda n: f"Colour {n}")
    slug = factory.Sequence(lambda n: f"colour-{n}")


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
    category = factory.SubFactory(CategoryFactory)
    base_price = Decimal("1000.00")


class ProductVariantFactory(DjangoModelFactory[ProductVariant]):
    class Meta:
        model = ProductVariant

    product = factory.SubFactory(ProductFactory)
    size = factory.SubFactory(SizeFactory)
    color = factory.SubFactory(ColorFactory)
    sku = factory.Sequence(lambda n: f"SKU-{n}")


class ProductImageFactory(DjangoModelFactory[ProductImage]):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = factory.django.ImageField(filename="product.jpg")
