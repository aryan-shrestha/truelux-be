import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from apps.catalog.management.commands._seed_catalogue import BRANDS, PRODUCTS
from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Shade,
    Size,
)


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

    assert roots == {"skincare", "makeup", "haircare", "fragrance", "body"}
    assert set(Category.objects.filter(parent__slug="makeup").values_list("slug", flat=True)) == {
        "face",
        "eyes",
        "lips",
    }
    assert not Category.objects.filter(parent__parent__isnull=False).exists()


@pytest.mark.django_db
def test_foundations_and_lipsticks_come_in_four_to_six_shades(seeded):
    for slug in ("silk-foundation", "velvet-matte-lipstick", "satin-lip-crayon"):
        shades = ProductVariant.objects.filter(product__slug=slug, shade__isnull=False)

        assert 4 <= shades.count() <= 6


@pytest.mark.django_db
def test_perfumes_come_in_50_and_100_ml(seeded):
    sizes = set(
        ProductVariant.objects.filter(product__category__slug="fragrance").values_list(
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
    assert not Product.objects.get(slug="shea-body-butter").images.exists()
    assert not ProductVariant.objects.filter(
        product__slug="saffron-glow-oil", stock_quantity__gt=0
    ).exists()
    assert ProductVariant.objects.filter(price_override__isnull=False).exists()
    assert ProductVariant.objects.filter(stock_quantity__lte=5).count() >= 5


@pytest.mark.django_db
def test_running_twice_creates_no_duplicates(seeded):
    call_command("seed_demo")

    assert Product.objects.count() == len(PRODUCTS)
    assert Brand.objects.count() == len(BRANDS)
    assert Shade.objects.filter(slug="warm-beige").count() == 1
    assert Size.objects.filter(slug="30-ml").count() == 1


@pytest.mark.django_db
def test_flush_removes_the_seeded_products_and_reseeds(seeded):
    call_command("seed_demo", flush=True)

    assert Product.objects.count() == len(PRODUCTS)
    assert ProductVariant.objects.filter(product__slug="silk-foundation").count() == 6


@pytest.mark.django_db
def test_every_product_with_images_has_exactly_one_primary(seeded):
    for product in Product.objects.filter(images__isnull=False).distinct():
        assert product.images.filter(is_primary=True).count() == 1


@pytest.mark.django_db
def test_seeded_images_are_generated_pngs(seeded):
    image = ProductImage.objects.get(product__slug="silk-foundation", is_primary=True)

    with Image.open(image.image.path) as png:
        assert png.format == "PNG"
        assert png.size == (800, 1000)
