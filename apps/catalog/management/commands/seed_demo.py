"""Populate a development catalogue.

`size` and `color` ship empty and nothing populates them, so a fresh database
cannot hold a single variant and the API serves an empty catalogue. Until
`merchant-admin` (#10) exists, this is how a developer gets something to look at.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import ProtectedError

from apps.catalog.models import Category, Color, Product, ProductImage, ProductVariant, Size

ASSET_DIR = Path(__file__).resolve().parent / "seed_assets"

SIZES: tuple[tuple[str, str], ...] = (
    ("XS", "xs"),
    ("S", "s"),
    ("M", "m"),
    ("L", "l"),
    ("XL", "xl"),
    ("XXL", "xxl"),
)

COLORS: tuple[tuple[str, str], ...] = (
    ("Black", "black"),
    ("Bone", "bone"),
    ("Washed Indigo", "washed-indigo"),
    ("Olive", "olive"),
    ("Rust", "rust"),
)

CATEGORIES: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    ("Tops", "tops", (("Tees", "tees"), ("Hoodies", "hoodies"))),
    ("Bottoms", "bottoms", (("Cargos", "cargos"), ("Shorts", "shorts"))),
)


@dataclass(frozen=True)
class VariantSpec:
    size: str
    color: str
    stock: int
    price_override: Decimal | None = None


@dataclass(frozen=True)
class ProductSpec:
    name: str
    slug: str
    category: str
    base_price: Decimal
    description: str
    variants: tuple[VariantSpec, ...]
    images: tuple[str, ...] = ()
    is_published: bool = True
    sort_order: int = 0
    notes: str = ""
    alt_text: str = field(default="")


# Deliberately uneven. Every awkward shape the storefront has to survive is here,
# because the ones that break a product page are absent from a tidy fixture: a
# product with no photograph, one with a single variant, a sparse variant set
# where a size exists in only one colour, a variant priced above its product, a
# product with nothing in stock, and one that is unpublished and must never
# appear in the API at all.
PRODUCTS: tuple[ProductSpec, ...] = (
    ProductSpec(
        name="Boxy Logo Tee",
        slug="boxy-logo-tee",
        category="tees",
        base_price=Decimal("2400.00"),
        description=(
            "A wide, short tee cut from heavyweight cotton, screen-printed one colour "
            "at a time. It is meant to sit away from the body and to keep its shape "
            "after the wash that ruins a lighter shirt."
        ),
        alt_text="Boxy logo tee, front",
        variants=(
            VariantSpec("s", "black", 6),
            VariantSpec("m", "black", 12),
            VariantSpec("l", "black", 9),
            VariantSpec("xl", "black", 3),
            VariantSpec("s", "bone", 4),
            VariantSpec("m", "bone", 7),
            VariantSpec("l", "bone", 0),
        ),
        images=("shot-01.jpg", "shot-02.jpg", "shot-03.jpg"),
        sort_order=10,
        notes="The ordinary case: several sizes, two colours, one colour partly sold out.",
    ),
    ProductSpec(
        name="Washed Pocket Tee",
        slug="washed-pocket-tee",
        category="tees",
        base_price=Decimal("2650.00"),
        description=(
            "Garment-dyed after cutting, so no two are exactly the same shade and "
            "the seams hold the colour longest. One chest pocket, bar-tacked."
        ),
        alt_text="Washed pocket tee on a rail",
        variants=(
            VariantSpec("m", "washed-indigo", 5),
            VariantSpec("l", "washed-indigo", 8),
            VariantSpec("xl", "washed-indigo", 2),
            # XXL costs more and exists in this colour only: the sparse-grid case
            # the variant picker has to tell apart from "sold out".
            VariantSpec("xxl", "washed-indigo", 4, price_override=Decimal("2950.00")),
            VariantSpec("m", "olive", 3),
            VariantSpec("l", "olive", 0),
        ),
        images=("shot-04.jpg", "shot-05.jpg"),
        sort_order=20,
        notes="Carries a price_override, and a size that exists in one colour only.",
    ),
    ProductSpec(
        name="Heavy Fleece Hoodie",
        slug="heavy-fleece-hoodie",
        category="hoodies",
        base_price=Decimal("6200.00"),
        description=(
            "Four hundred and eighty gram loopback fleece, unbrushed inside so it "
            "keeps its surface. Ribbed cuffs, a lined hood, and a kangaroo pocket "
            "deep enough to be useful."
        ),
        alt_text="Heavy fleece hoodie, three-quarter view",
        variants=(
            VariantSpec("s", "black", 2),
            VariantSpec("m", "black", 6),
            VariantSpec("l", "black", 6),
            VariantSpec("xl", "black", 1),
            VariantSpec("m", "rust", 4),
            VariantSpec("l", "rust", 5),
            VariantSpec("xl", "rust", 0),
        ),
        images=("shot-06.jpg", "shot-07.jpg"),
        sort_order=30,
    ),
    ProductSpec(
        name="Zip Through Hoodie",
        slug="zip-through-hoodie",
        category="hoodies",
        base_price=Decimal("6800.00"),
        description=(
            "The same fleece with a full-length zip and a taller collar, so it "
            "works as the outer layer through most of a Kathmandu winter."
        ),
        alt_text="Zip through hoodie, front",
        variants=(
            VariantSpec("m", "bone", 3),
            VariantSpec("l", "bone", 4),
            VariantSpec("l", "olive", 2),
        ),
        images=("shot-08.jpg",),
        sort_order=40,
    ),
    ProductSpec(
        name="Utility Cargo Pant",
        slug="utility-cargo-pant",
        category="cargos",
        base_price=Decimal("5400.00"),
        description=(
            "Cotton ripstop with a relaxed leg and two bellowed pockets that hold "
            "their shape when empty. Cut long on purpose; they are meant to stack."
        ),
        alt_text="Utility cargo pant, side",
        variants=(
            VariantSpec("s", "olive", 4),
            VariantSpec("m", "olive", 7),
            VariantSpec("l", "olive", 5),
            VariantSpec("xl", "olive", 2),
            VariantSpec("m", "black", 6),
            VariantSpec("l", "black", 3),
        ),
        images=("shot-09.jpg", "shot-10.jpg"),
        sort_order=50,
    ),
    ProductSpec(
        name="Pleated Wide Short",
        slug="pleated-wide-short",
        category="shorts",
        base_price=Decimal("3200.00"),
        description=(
            "A single deep pleat at each hip, cut wide and finished just above the "
            "knee. Heavier than a short usually is, so it hangs instead of flapping."
        ),
        alt_text="",
        variants=(
            VariantSpec("m", "bone", 5),
            VariantSpec("l", "bone", 6),
            VariantSpec("m", "rust", 3),
        ),
        # No images at all: the card and the gallery both have to survive it, and
        # nothing in the backend requires a merchant to add one.
        images=(),
        sort_order=60,
        notes="No images. Also an empty alt_text on purpose, which means decorative.",
    ),
    ProductSpec(
        name="Single Stitch Cap",
        slug="single-stitch-cap",
        category="tees",
        base_price=Decimal("1800.00"),
        description="Six panels, unstructured, one size. Cotton twill with a curved brim.",
        alt_text="Single stitch cap",
        # One variant, and a garment with no real size axis still needs a size row
        # to point at -- "One Size" would be the honest one, but the size table is
        # a fixed run, so this uses M and the storefront renders a label rather
        # than a picker.
        variants=(VariantSpec("m", "black", 14),),
        images=("shot-11.jpg",),
        sort_order=70,
        notes="Single variant: the picker must render a label, not a group of one.",
    ),
    ProductSpec(
        name="Overdyed Work Jacket",
        slug="overdyed-work-jacket",
        category="tops",
        base_price=Decimal("7900.00"),
        description=(
            "A chore jacket overdyed in one lot, so the thread takes the colour "
            "differently from the cloth and the seams read a shade darker."
        ),
        alt_text="Overdyed work jacket",
        # Nothing in stock anywhere: the sold-out product, which still has to be
        # browsable and must not offer an add to bag.
        variants=(
            VariantSpec("m", "rust", 0),
            VariantSpec("l", "rust", 0),
            VariantSpec("xl", "rust", 0),
        ),
        images=("shot-12.jpg",),
        sort_order=80,
        notes="Entirely sold out.",
    ),
    ProductSpec(
        name="Unreleased Drop Tee",
        slug="unreleased-drop-tee",
        category="tees",
        base_price=Decimal("2500.00"),
        description="Not for sale yet. If this appears in the API, visibility scoping is broken.",
        alt_text="Unreleased tee",
        variants=(VariantSpec("m", "black", 10),),
        images=("shot-01.jpg",),
        is_published=False,
        sort_order=90,
        notes="Unpublished. Must never appear in any API response.",
    ),
)

SEEDED_SLUGS = tuple(spec.slug for spec in PRODUCTS)


class Command(BaseCommand):
    help = "Populate a development catalogue. Refuses to run outside DEBUG."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete the products this command created before seeding again.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # This writes rows. A seed command pointed at production by a mistyped
        # DJANGO_SETTINGS_MODULE would put fake garments in a real shop, so the
        # guard is a refusal rather than a warning.
        if not settings.DEBUG:
            raise CommandError("seed_demo writes demo rows and only runs with DEBUG enabled.")

        if not ASSET_DIR.is_dir():
            raise CommandError(f"Seed images are missing: {ASSET_DIR}")

        if options["flush"]:
            self._flush()

        with transaction.atomic():
            sizes = self._seed_sizes()
            colors = self._seed_colors()
            categories = self._seed_categories()
            created, updated = self._seed_products(sizes, colors, categories)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(sizes)} sizes, {len(colors)} colours, {len(categories)} categories, "
                f"{created} new products ({updated} already present)."
            )
        )
        self.stdout.write(
            "One product is unpublished and one is entirely sold out, on purpose. "
            "See the module docstring."
        )

    def _flush(self) -> None:
        # Sizes, colours and categories are left alone: PROTECT on the variant
        # foreign keys means they cannot be deleted while anything references
        # them, and get_or_create makes re-seeding them free anyway.
        try:
            deleted, _ = Product.objects.filter(slug__in=SEEDED_SLUGS).delete()
        except ProtectedError as exc:
            # OrderItem.variant is PROTECT, so an order placed against a seeded
            # variant blocks this. Saying which command releases it beats a
            # traceback naming a foreign key.
            raise CommandError(
                "Seeded products are referenced by existing orders. "
                "Run `manage.py seed_orders --flush` first."
            ) from exc
        self.stdout.write(f"Flushed {deleted} rows for {len(SEEDED_SLUGS)} seeded products.")

    def _seed_sizes(self) -> dict[str, Size]:
        sizes: dict[str, Size] = {}
        for order, (name, slug) in enumerate(SIZES):
            size, _ = Size.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "sort_order": order},
            )
            sizes[slug] = size
        return sizes

    def _seed_colors(self) -> dict[str, Color]:
        colors: dict[str, Color] = {}
        for order, (name, slug) in enumerate(COLORS):
            color, _ = Color.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "sort_order": order},
            )
            colors[slug] = color
        return colors

    def _seed_categories(self) -> dict[str, Category]:
        categories: dict[str, Category] = {}
        for order, (name, slug, children) in enumerate(CATEGORIES):
            parent, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "sort_order": order},
            )
            categories[slug] = parent

            for child_order, (child_name, child_slug) in enumerate(children):
                child, _ = Category.objects.get_or_create(
                    slug=child_slug,
                    defaults={
                        "name": child_name,
                        "parent": parent,
                        "sort_order": child_order,
                    },
                )
                categories[child_slug] = child
        return categories

    def _seed_products(
        self,
        sizes: dict[str, Size],
        colors: dict[str, Color],
        categories: dict[str, Category],
    ) -> tuple[int, int]:
        created_count = 0
        updated_count = 0

        for spec in PRODUCTS:
            product, created = Product.objects.get_or_create(
                slug=spec.slug,
                defaults={
                    "name": spec.name,
                    "description": spec.description,
                    "category": categories[spec.category],
                    "base_price": spec.base_price,
                    "is_published": spec.is_published,
                    "sort_order": spec.sort_order,
                },
            )
            if not created:
                updated_count += 1
                continue

            created_count += 1
            self._seed_variants(product, spec, sizes, colors)
            self._seed_images(product, spec)

        return created_count, updated_count

    def _seed_variants(
        self,
        product: Product,
        spec: ProductSpec,
        sizes: dict[str, Size],
        colors: dict[str, Color],
    ) -> None:
        prefix = "".join(word[0] for word in spec.name.split())[:4].upper()

        ProductVariant.objects.bulk_create(
            ProductVariant(
                product=product,
                size=sizes[variant.size],
                color=colors[variant.color],
                sku=f"{prefix}-{variant.size.upper()}-{variant.color.upper()[:3]}",
                stock_quantity=variant.stock,
                price_override=variant.price_override,
            )
            for variant in spec.variants
        )

    def _seed_images(self, product: Product, spec: ProductSpec) -> None:
        for order, filename in enumerate(spec.images):
            source = ASSET_DIR / filename
            if not source.is_file():
                raise CommandError(f"Seed image is missing: {source}")

            image = ProductImage(
                product=product,
                alt_text=spec.alt_text,
                sort_order=order,
                is_primary=order == 0,
            )
            with source.open("rb") as handle:
                # A distinct name per product: the same file backs several products
                # and the storage backend would otherwise suffix the collisions.
                image.image.save(f"{product.slug}-{order}.jpg", File(handle), save=False)
            image.save()
