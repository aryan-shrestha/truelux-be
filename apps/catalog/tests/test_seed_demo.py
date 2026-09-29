from io import BytesIO
from urllib.error import URLError

import pytest
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from apps.catalog.management.commands import seed_demo
from apps.catalog.management.commands._seed_catalogue import BRANDS, PRODUCTS, SKIN_TYPES
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
from apps.catalog.tests.factories import BrandFactory, CategoryFactory, ProductFactory

# Bound at import, before conftest replaces the module attribute for every test.
real_fetch_image = seed_demo.fetch_image


@pytest.fixture
def seeded(db, settings, tmp_path):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo")


@pytest.mark.django_db
def test_seeding_outside_debug_is_refused(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_demo")

    assert not Product.objects.exists()


@pytest.mark.django_db
def test_seed_creates_brands_with_logos(seeded):
    assert Brand.objects.count() == len(BRANDS)
    assert not Brand.objects.filter(logo="").exists()


@pytest.mark.django_db
def test_seed_creates_the_cosmetics_category_tree(seeded):
    roots = set(Category.objects.filter(parent__isnull=True).values_list("slug", flat=True))

    assert roots == {"skincare", "makeup", "body", "fragrance", "haircare"}
    assert list(
        Category.objects.filter(parent__slug="skincare").values_list("name", flat=True)
    ) == ["Cleanse", "Exfoliate", "Treat & Masque", "Tone", "Hydrate", "Eyes & Lips", "Sun Care"]
    assert list(Category.objects.filter(parent__slug="body").values_list("name", flat=True)) == [
        "Creams, Oils & Scrubs",
        "Shower & Bath",
        "Balms",
        "Hands & Feet",
        "Sun Protection",
    ]
    assert list(Category.objects.filter(parent__slug="makeup").values_list("slug", flat=True)) == [
        "face",
        "eyes",
        "lips",
    ]
    assert list(
        Category.objects.filter(parent__slug="fragrance").values_list("slug", flat=True)
    ) == ["perfume", "essential-oils"]
    assert not Category.objects.filter(parent__slug="haircare").exists()
    assert not Category.objects.filter(parent__parent__isnull=False).exists()


@pytest.mark.django_db
def test_every_child_category_has_at_least_two_published_products(seeded):
    for category in Category.objects.filter(parent__isnull=False):
        assert category.products.filter(is_published=True).count() >= 2, category.slug


@pytest.mark.django_db
def test_skincare_and_body_products_carry_care_details(seeded):
    assert SkinType.objects.count() == len(SKIN_TYPES)
    for product in Product.objects.filter(category__parent__slug__in=("skincare", "body")):
        assert 1 <= product.skin_types.count() <= 4, product.slug
        assert product.skin_feel, product.slug
        assert product.key_ingredients, product.slug


@pytest.mark.django_db
def test_foundations_and_lip_tints_come_in_four_to_six_shades(seeded):
    for slug in (
        "tirtir-mask-fit-red-cushion",
        "romand-juicy-lasting-tint",
        "peripera-ink-the-velvet",
    ):
        shades = ProductVariant.objects.filter(product__slug=slug, shade__isnull=False)

        assert 4 <= shades.count() <= 6


@pytest.mark.django_db
def test_perfumes_come_in_50_and_100_ml(seeded):
    sizes = set(
        ProductVariant.objects.filter(product__category__slug="perfume").values_list(
            "size__slug", flat=True
        )
    )

    assert sizes == {"50-ml", "100-ml"}


@pytest.mark.django_db
def test_skincare_is_shadeless(seeded):
    assert not ProductVariant.objects.filter(
        product__category__parent__slug="skincare", shade__isnull=False
    ).exists()


@pytest.mark.django_db
def test_seed_includes_the_shapes_the_storefront_has_to_survive(seeded):
    assert Product.objects.filter(is_published=False).count() == 1
    assert not Product.objects.get(slug="illiyoon-ceramide-ato-lotion").images.exists()
    assert not ProductVariant.objects.filter(
        product__slug="sulwhasoo-first-care-activating-serum", stock_quantity__gt=0
    ).exists()
    assert ProductVariant.objects.filter(price_override__isnull=False).exists()
    assert ProductVariant.objects.filter(stock_quantity__lte=5).count() >= 5


def test_the_seed_data_puts_six_variants_on_sale_by_override_and_by_base_price():
    sale_variants = [
        (product, variant, variant.compare_at_price)
        for product in PRODUCTS
        for variant in product.variants
        if variant.compare_at_price is not None
    ]

    assert len(sale_variants) == 6
    assert {variant.price_override is None for _, variant, _ in sale_variants} == {True, False}
    for product, variant, compare_at in sale_variants:
        assert compare_at > (variant.price_override or product.base_price), product.slug
        assert product.is_published, product.slug


@pytest.mark.django_db
def test_seeded_sale_variants_are_on_sale(seeded):
    sale_variants = ProductVariant.objects.filter(compare_at_price__isnull=False).select_related(
        "product"
    )

    assert sale_variants.count() == 6
    assert all(variant.on_sale for variant in sale_variants)


@pytest.mark.django_db
def test_running_twice_creates_no_duplicates(seeded):
    call_command("seed_demo")

    assert Product.objects.count() == len(PRODUCTS)
    assert Brand.objects.count() == len(BRANDS)
    assert Shade.objects.filter(slug="tirtir-21n-ivory").count() == 1
    assert Size.objects.filter(slug="30-ml").count() == 1


@pytest.mark.django_db
def test_flush_removes_the_seeded_products_and_reseeds(seeded):
    call_command("seed_demo", flush=True)

    assert Product.objects.count() == len(PRODUCTS)
    assert ProductVariant.objects.filter(product__slug="tirtir-mask-fit-red-cushion").count() == 6


@pytest.mark.django_db
def test_flush_replaces_a_retired_category_tree(seeded):
    retired = Category.objects.create(
        name="Cleansers", slug="cleansers", parent=Category.objects.get(slug="skincare")
    )
    Product.objects.filter(slug="round-lab-1025-dokdo-cleanser").update(category=retired)
    Category.objects.filter(slug="tone").update(parent=None)

    call_command("seed_demo", flush=True)

    assert not Category.objects.filter(slug="cleansers").exists()
    assert Category.objects.filter(slug="tone", parent__slug="skincare").exists()
    assert Product.objects.get(slug="round-lab-1025-dokdo-cleanser").category.slug == "cleanse"


@pytest.mark.django_db
def test_flush_keeps_a_seeded_category_holding_a_merchant_product(seeded):
    ProductFactory(category=Category.objects.get(slug="balms"))

    call_command("seed_demo", flush=True)

    assert Category.objects.filter(slug="balms").count() == 1


@pytest.mark.django_db
def test_every_product_with_images_has_exactly_one_primary(seeded):
    for product in Product.objects.filter(images__isnull=False).distinct():
        assert product.images.filter(is_primary=True).count() == 1


@pytest.mark.django_db
def test_seeded_images_and_logos_are_the_downloaded_files(seeded, seed_image_png):
    image = ProductImage.objects.get(product__slug="tirtir-mask-fit-red-cushion", is_primary=True)
    logo = Brand.objects.get(slug="tirtir").logo

    for stored in (image.image, logo):
        with stored.open("rb") as file:
            assert file.read() == seed_image_png


@pytest.mark.django_db
def test_an_image_that_cannot_be_downloaded_becomes_a_placeholder(settings, tmp_path, monkeypatch):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(seed_demo, "fetch_image", lambda url: None)

    call_command("seed_demo")

    image = ProductImage.objects.get(product__slug="tirtir-mask-fit-red-cushion", is_primary=True)
    with Image.open(image.image.path) as png:
        assert png.format == "PNG"
        assert png.size == (800, 1000)
    with Image.open(Brand.objects.get(slug="tirtir").logo.path) as png:
        assert png.size == (400, 400)
    assert Product.objects.count() == len(PRODUCTS)


def test_fetch_image_returns_the_bytes_and_extension_of_an_image(monkeypatch, seed_image_png):
    monkeypatch.setattr(seed_demo, "urlopen", lambda request, timeout: BytesIO(seed_image_png))

    assert real_fetch_image("https://cdn.example/photo.png") == (seed_image_png, "png")


def test_fetch_image_rejects_a_page_that_is_not_an_image(monkeypatch):
    monkeypatch.setattr(
        seed_demo, "urlopen", lambda request, timeout: BytesIO(b"<html>Not found</html>")
    )

    assert real_fetch_image("https://cdn.example/photo.png") is None


def test_fetch_image_returns_none_when_the_download_fails(monkeypatch):
    def unreachable(request, timeout):
        raise URLError("unreachable")

    monkeypatch.setattr(seed_demo, "urlopen", unreachable)

    assert real_fetch_image("https://cdn.example/photo.png") is None


@pytest.mark.django_db
def test_flush_removes_the_retired_invented_catalogue(seeded):
    retired_brand = BrandFactory(name="Lumière", slug="lumiere")
    ProductFactory(slug="silk-foundation", brand=retired_brand)
    kept_brand = BrandFactory(name="Aurum", slug="aurum")
    merchant_product = ProductFactory(brand=kept_brand)

    call_command("seed_demo", flush=True)

    assert not Product.objects.filter(slug="silk-foundation").exists()
    assert not Brand.objects.filter(slug="lumiere").exists()
    assert Brand.objects.filter(slug="aurum").exists()
    assert Product.objects.filter(pk=merchant_product.pk).exists()


@pytest.mark.django_db
def test_flush_reparents_a_surviving_seeded_category(seeded):
    cleanse = Category.objects.get(slug="cleanse")
    ProductFactory(category=cleanse)
    Category.objects.filter(pk=cleanse.pk).update(name="Old Cleansers", sort_order=99)

    call_command("seed_demo", flush=True)

    cleanse.refresh_from_db()
    assert cleanse.parent is not None
    assert cleanse.parent.slug == "skincare"
    assert (cleanse.name, cleanse.sort_order) == ("Cleanse", 0)
    assert Category.objects.filter(parent__slug="skincare").first() == cleanse


@pytest.mark.django_db
def test_reseeding_restores_a_seeded_product_and_category(seeded):
    Category.objects.filter(slug="tone").update(parent=None, name="Toners", sort_order=42)
    Product.objects.filter(slug="round-lab-1025-dokdo-cleanser").update(
        name="Renamed", category=Category.objects.get(slug="lips"), is_published=False
    )

    call_command("seed_demo")

    tone = Category.objects.get(slug="tone")
    assert (tone.parent.slug if tone.parent else None, tone.name, tone.sort_order) == (
        "skincare",
        "Tone",
        3,
    )
    product = Product.objects.get(slug="round-lab-1025-dokdo-cleanser")
    assert (product.name, product.category.slug, product.is_published) == (
        "1025 Dokdo Cleanser",
        "cleanse",
        True,
    )


@pytest.fixture
def deploying(db, settings, tmp_path):
    settings.DEBUG = False
    settings.SEED_DEMO_DATA = True
    settings.MEDIA_ROOT = tmp_path


def test_deploy_seeds_an_empty_catalogue_outside_debug(deploying):
    call_command("seed_demo", "--deploy")

    assert Product.objects.count() == len(PRODUCTS)
    image = ProductImage.objects.get(product__slug="tirtir-mask-fit-red-cushion", is_primary=True)
    assert image.image.name
    assert default_storage.exists(image.image.name)


@pytest.mark.django_db
def test_deploy_is_a_no_op_while_seed_demo_data_is_false(settings):
    settings.DEBUG = False
    settings.SEED_DEMO_DATA = False

    call_command("seed_demo", "--deploy")

    assert not Product.objects.exists()


def test_deploy_leaves_an_existing_catalogue_alone(deploying):
    CategoryFactory(name="My Cleansers", slug="cleanse")

    call_command("seed_demo", "--deploy")

    assert list(Category.objects.values_list("name", flat=True)) == ["My Cleansers"]
    assert not Product.objects.exists()


def test_deploy_cannot_be_combined_with_flush(deploying):
    with pytest.raises(CommandError, match="not allowed with"):
        call_command("seed_demo", "--deploy", "--flush")
