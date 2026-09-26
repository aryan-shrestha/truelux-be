"""Populate a development cosmetics catalogue: brands, categories, sizes, shades,
skin types, products with variants, and generated placeholder images.
"""

import unicodedata
from io import BytesIO
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import ProtectedError
from PIL import Image, ImageDraw, ImageFont

from apps.catalog.management.commands._seed_catalogue import (
    BRANDS,
    CATEGORIES,
    PRODUCTS,
    RETIRED_CATEGORY_SLUGS,
    SHADES,
    SIZES,
    SKIN_TYPES,
    BrandSpec,
    ProductSpec,
)
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

SEEDED_SLUGS = tuple(spec.slug for spec in PRODUCTS)
SEEDED_CATEGORY_SLUGS = (
    *(slug for _, slug, _ in CATEGORIES),
    *(child_slug for _, _, children in CATEGORIES for _, child_slug in children),
    *RETIRED_CATEGORY_SLUGS,
)
IMAGE_SIZE = (800, 1000)
LOGO_SIZE = (400, 400)


def initials(name: str, limit: int = 3) -> str:
    return "".join(word[0] for word in name.replace("&", " ").split() if word[0].isalnum())[
        :limit
    ].upper()


def ascii_caption(text: str) -> str:
    # Pillow's bundled font has no glyphs for accented letters such as the è in Lumière.
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return folded.upper()


def placeholder_png(
    *, text: str, caption: str, top: str, bottom: str, size: tuple[int, int]
) -> bytes:
    mask = Image.linear_gradient("L").resize(size)
    image = Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask)
    draw = ImageDraw.Draw(image)
    width, height = size

    draw.text(
        (width / 2, height / 2),
        text,
        fill="#FFFFFF",
        font=ImageFont.load_default(size=height // 4),
        anchor="mm",
    )
    draw.text(
        (width / 2, height - height // 10),
        ascii_caption(caption),
        fill="#FFFFFF",
        font=ImageFont.load_default(size=height // 24),
        anchor="mm",
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Populate a development cosmetics catalogue. Refuses to run outside DEBUG."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete the products and categories this command created before seeding again.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # A mistyped DJANGO_SETTINGS_MODULE must not put demo products in a real shop.
        if not settings.DEBUG:
            raise CommandError("seed_demo writes demo rows and only runs with DEBUG enabled.")

        if options["flush"]:
            self._flush()

        with transaction.atomic():
            brands = self._seed_brands()
            sizes = self._seed_sizes()
            shades = self._seed_shades()
            skin_types = self._seed_skin_types()
            categories = self._seed_categories()
            created, existing = self._seed_products(brands, sizes, shades, skin_types, categories)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(brands)} brands, {len(categories)} categories, {len(sizes)} sizes, "
                f"{len(shades)} shades, {len(skin_types)} skin types, {created} new products "
                f"({existing} already present)."
            )
        )

    def _flush(self) -> None:
        # Brands, sizes, shades and skin types are left alone: PROTECT keeps most of them
        # while anything refers to them, and get_or_create makes re-seeding them free.
        try:
            deleted, _ = Product.objects.filter(slug__in=SEEDED_SLUGS).delete()
        except ProtectedError as exc:
            raise CommandError(
                "Seeded products are referenced by existing orders. "
                "Run `manage.py seed_orders --flush-only` first."
            ) from exc
        self.stdout.write(f"Flushed {deleted} rows for {len(SEEDED_SLUGS)} seeded products.")

        # Categories are recreated so a reshaped tree replaces the old one; a category
        # still holding a product the merchant added is kept.
        deleted, _ = Category.objects.filter(
            slug__in=SEEDED_CATEGORY_SLUGS, products__isnull=True
        ).delete()
        self.stdout.write(f"Flushed {deleted} seeded categories.")

    def _seed_brands(self) -> dict[str, Brand]:
        brands: dict[str, Brand] = {}
        for order, spec in enumerate(BRANDS):
            brand, created = Brand.objects.get_or_create(
                slug=spec.slug,
                defaults={"name": spec.name, "description": spec.description, "sort_order": order},
            )
            if created:
                self._attach_logo(brand, spec)
            brands[spec.slug] = brand
        return brands

    def _attach_logo(self, brand: Brand, spec: BrandSpec) -> None:
        png = placeholder_png(
            text=initials(spec.name, limit=2),
            caption=spec.name,
            top=spec.palette[0],
            bottom=spec.palette[1],
            size=LOGO_SIZE,
        )
        brand.logo.save(f"{spec.slug}.png", ContentFile(png), save=True)

    def _seed_sizes(self) -> dict[str, Size]:
        sizes: dict[str, Size] = {}
        for order, (name, slug) in enumerate(SIZES):
            size, _ = Size.objects.get_or_create(
                slug=slug, defaults={"name": name, "sort_order": order}
            )
            sizes[slug] = size
        return sizes

    def _seed_shades(self) -> dict[str, Shade]:
        shades: dict[str, Shade] = {}
        for order, (name, slug, hex_code) in enumerate(SHADES):
            shade, _ = Shade.objects.get_or_create(
                slug=slug, defaults={"name": name, "hex_code": hex_code, "sort_order": order}
            )
            shades[slug] = shade
        return shades

    def _seed_skin_types(self) -> dict[str, SkinType]:
        skin_types: dict[str, SkinType] = {}
        for order, (name, slug) in enumerate(SKIN_TYPES):
            skin_type, _ = SkinType.objects.get_or_create(
                slug=slug, defaults={"name": name, "sort_order": order}
            )
            skin_types[slug] = skin_type
        return skin_types

    def _seed_categories(self) -> dict[str, Category]:
        categories: dict[str, Category] = {}
        for order, (name, slug, children) in enumerate(CATEGORIES):
            parent, _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": name, "sort_order": order}
            )
            categories[slug] = parent

            for child_order, (child_name, child_slug) in enumerate(children):
                child, _ = Category.objects.get_or_create(
                    slug=child_slug,
                    defaults={"name": child_name, "parent": parent, "sort_order": child_order},
                )
                categories[child_slug] = child
        return categories

    def _seed_products(
        self,
        brands: dict[str, Brand],
        sizes: dict[str, Size],
        shades: dict[str, Shade],
        skin_types: dict[str, SkinType],
        categories: dict[str, Category],
    ) -> tuple[int, int]:
        created_count = 0
        brand_specs = {spec.slug: spec for spec in BRANDS}

        for order, spec in enumerate(PRODUCTS):
            product, created = Product.objects.get_or_create(
                slug=spec.slug,
                defaults={
                    "name": spec.name,
                    "description": spec.description,
                    "brand": brands[spec.brand],
                    "category": categories[spec.category],
                    "base_price": spec.base_price,
                    "is_published": spec.is_published,
                    "sort_order": order * 10,
                    "skin_feel": spec.skin_feel,
                    "key_ingredients": spec.key_ingredients,
                },
            )
            if not created:
                continue

            created_count += 1
            product.skin_types.set(skin_types[slug] for slug in spec.skin_types)
            brand_spec = brand_specs[spec.brand]
            self._seed_variants(product, spec, brand_spec, sizes, shades)
            self._seed_images(product, spec, brand_spec)

        return created_count, len(PRODUCTS) - created_count

    def _seed_variants(
        self,
        product: Product,
        spec: ProductSpec,
        brand_spec: BrandSpec,
        sizes: dict[str, Size],
        shades: dict[str, Shade],
    ) -> None:
        stem = f"{brand_spec.code}-{initials(spec.name, limit=4)}"
        ProductVariant.objects.bulk_create(
            ProductVariant(
                product=product,
                size=sizes[variant.size],
                shade=shades[variant.shade] if variant.shade else None,
                sku="-".join(
                    part
                    for part in (
                        stem,
                        variant.size.replace("-", "").upper(),
                        initials(shades[variant.shade].name) if variant.shade else "",
                    )
                    if part
                ),
                stock_quantity=variant.stock,
                price_override=variant.price_override,
            )
            for variant in spec.variants
        )

    def _seed_images(self, product: Product, spec: ProductSpec, brand_spec: BrandSpec) -> None:
        top, bottom = brand_spec.palette
        for order in range(spec.image_count):
            png = placeholder_png(
                text=initials(spec.name, limit=2),
                caption=brand_spec.name,
                top=top if order == 0 else bottom,
                bottom=bottom if order == 0 else top,
                size=IMAGE_SIZE,
            )
            image = ProductImage(
                product=product,
                alt_text=f"{brand_spec.name} {spec.name}",
                sort_order=order,
                is_primary=order == 0,
            )
            image.image.save(f"{product.slug}-{order}.png", ContentFile(png), save=False)
            image.save()
