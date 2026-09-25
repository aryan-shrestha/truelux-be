import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import Category, Color, Product, ProductImage, ProductVariant, Size


@pytest.fixture
def seeded(db, settings, tmp_path):
    settings.DEBUG = True
    # test.py points STORAGES at a filesystem backend already; this keeps the
    # seeded images out of the repository's own media directory.
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo")


@pytest.mark.django_db
def test_seeding_outside_debug_is_refused(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_demo")

    assert not Product.objects.exists()


@pytest.mark.django_db
def test_seed_populates_the_lookup_tables_a_variant_needs(seeded):
    # Both ship empty, and an empty size table means no variant can exist at all.
    assert Size.objects.count() == 6
    assert Color.objects.count() == 5


@pytest.mark.django_db
def test_seed_creates_a_one_level_category_tree(seeded):
    assert Category.objects.filter(parent__isnull=True).count() == 2
    assert Category.objects.filter(parent__isnull=False).count() == 4
    # Category.parent allows one level and nothing in the database enforces it,
    # so the seed must not be the thing that builds a deeper tree.
    assert not Category.objects.filter(parent__parent__isnull=False).exists()


@pytest.mark.django_db
def test_seed_leaves_one_product_unpublished(seeded):
    assert Product.objects.count() == 9
    assert Product.objects.filter(is_published=True).count() == 8
    assert Product.objects.get(slug="unreleased-drop-tee").is_published is False


@pytest.mark.django_db
def test_running_twice_creates_no_duplicates(seeded):
    call_command("seed_demo")

    assert Product.objects.count() == 9
    assert Size.objects.count() == 6
    assert ProductVariant.objects.filter(sku="BLT-M-BLA").count() == 1


@pytest.mark.django_db
def test_flush_removes_the_seeded_products_and_reseeds(seeded):
    call_command("seed_demo", flush=True)

    assert Product.objects.count() == 9
    assert ProductVariant.objects.filter(product__slug="boxy-logo-tee").count() == 7


@pytest.mark.django_db
def test_seed_includes_the_shapes_the_storefront_has_to_survive(seeded):
    # Each of these is a state a merchant can produce and a tidy fixture omits.
    assert not Product.objects.get(slug="pleated-wide-short").images.exists()
    assert Product.objects.get(slug="single-stitch-cap").variants.count() == 1
    assert (
        ProductVariant.objects.filter(
            product__slug="overdyed-work-jacket", stock_quantity__gt=0
        ).count()
        == 0
    )
    assert (
        ProductVariant.objects.filter(
            product__slug="washed-pocket-tee", price_override__isnull=False
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_seed_gives_a_sparse_variant_grid_not_a_cartesian_product(seeded):
    # XXL exists in one colour only. A picker built from independent size and
    # colour lists would offer XXL in olive, which was never made.
    variants = ProductVariant.objects.filter(product__slug="washed-pocket-tee")

    assert variants.filter(size__slug="xxl").count() == 1
    assert (
        variants.count()
        < variants.values("size").distinct().count() * variants.values("color").distinct().count()
    )


@pytest.mark.django_db
def test_every_product_with_images_has_exactly_one_primary(seeded):
    for product in Product.objects.filter(images__isnull=False).distinct():
        assert product.images.filter(is_primary=True).count() == 1


@pytest.mark.django_db
def test_seeded_images_do_not_collide_between_products(seeded):
    # The same source file backs several products; without a per-product name the
    # storage backend would suffix the collisions and the names would drift.
    names = [image.image.name for image in ProductImage.objects.all()]

    assert len(names) == len(set(names))
