import threading

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db import connections
from django.urls import reverse

from apps.catalog.admin import generate_sku
from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import (
    ProductFactory,
    ProductImageFactory,
    ProductVariantFactory,
    ShadeFactory,
    SizeFactory,
)
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    staff = UserFactory.create(is_staff=True, is_superuser=True)
    client.force_login(staff)
    return client


def _generate(admin_client, product, sizes, shades):
    return admin_client.post(
        reverse("admin:catalog_product_changelist"),
        {
            "action": "generate_variants",
            ACTION_CHECKBOX_NAME: [str(product.pk)],
            "apply": "1",
            "sizes": [str(size.pk) for size in sizes],
            "shades": [str(shade.pk) for shade in shades],
        },
        follow=True,
    )


def test_generate_variants_creates_missing_combinations(admin_client):
    product = ProductFactory.create()
    sizes = [SizeFactory.create(slug=slug, name=slug.upper()) for slug in ("s", "m", "l")]
    shades = [ShadeFactory.create(slug=slug, name=slug.title()) for slug in ("black", "bone")]

    _generate(admin_client, product, sizes, shades)

    # Fifteen rows typed by hand is fifteen chances to mistype a SKU, which is why
    # this action exists at all.
    assert product.variants.count() == 6


@pytest.mark.parametrize(
    ("url_name", "action", "factory"),
    [
        ("admin:catalog_product_changelist", "generate_variants", ProductFactory),
        ("admin:catalog_productvariant_changelist", "adjust_stock", ProductVariantFactory),
    ],
)
def test_the_action_asks_before_it_acts(admin_client, url_name, action, factory):
    # The page the merchant sees on the first click. Every other test posts
    # apply=1 and skips it, so without this a broken template is a 500 nobody
    # finds until someone uses the admin.
    obj = factory.create()

    response = admin_client.post(
        reverse(url_name), {"action": action, ACTION_CHECKBOX_NAME: [str(obj.pk)]}
    )

    assert response.status_code == 200
    assert b"<form" in response.content
    assert b"csrfmiddlewaretoken" in response.content


def test_generate_variants_skips_existing_combinations(admin_client):
    product = ProductFactory.create()
    medium = SizeFactory.create(slug="m", name="M")
    black = ShadeFactory.create(slug="black", name="Black")
    ProductVariantFactory.create(product=product, size=medium, shade=black, sku="KEEP-ME")
    large = SizeFactory.create(slug="l", name="L")

    _generate(admin_client, product, [medium, large], [black])

    assert product.variants.count() == 2
    # The existing row keeps its own SKU rather than being recreated.
    assert product.variants.filter(sku="KEEP-ME").exists()


def test_generated_skus_do_not_collide_across_products(admin_client):
    # The scheme is built from the product slug precisely so that two products
    # whose names share initials cannot produce the same SKU.
    first = ProductFactory.create(name="Silk Foundation", slug="silk-foundation")
    second = ProductFactory.create(name="Soft Focus Primer", slug="soft-focus-primer")
    medium = SizeFactory.create(slug="m", name="M")
    black = ShadeFactory.create(slug="black", name="Black")

    _generate(admin_client, first, [medium], [black])
    _generate(admin_client, second, [medium], [black])

    skus = set(ProductVariant.objects.values_list("sku", flat=True))
    assert skus == {"SILK-FOUNDATION-M-BLACK", "SOFT-FOCUS-PRIMER-M-BLACK"}


def test_a_generated_sku_fits_the_column():
    product = ProductFactory.build(slug="a-product-with-an-unreasonably-long-slug-" + "x" * 40)
    size = SizeFactory.build(slug="xxl")
    shade = ShadeFactory.build(slug="rose-nude")

    sku = generate_sku(product=product, size=size, shade=shade)

    assert len(sku) <= 64
    assert sku.endswith("-XXL-ROSE-NUDE")


def test_a_truncated_slug_collision_is_reported_not_raised(admin_client):
    # The scheme is unique only while the slug fits. Two products agreeing in their
    # first forty-odd characters generate the same SKU, and the merchant can fix
    # that by shortening one -- but only if the action tells them instead of 500ing.
    stem = "summer-2026-limited-edition-heavyweight-cotton-oversized-tee"
    first = ProductFactory.create(slug=f"{stem}-black")
    second = ProductFactory.create(slug=f"{stem}-white")
    size = SizeFactory.create(slug="xxl", name="XXL")
    shade = ShadeFactory.create(slug="rose-nude", name="Rose Nude")

    _generate(admin_client, first, [size], [shade])
    response = _generate(admin_client, second, [size], [shade])

    assert response.status_code == 200
    assert first.variants.count() == 1
    assert second.variants.count() == 0
    messages = [str(message) for message in response.context["messages"]]
    assert any("already taken" in message for message in messages)


def test_stock_is_not_editable_through_the_variant_inline(admin_client):
    variant = ProductVariantFactory.create(stock_quantity=5)

    response = admin_client.get(reverse("admin:catalog_product_change", args=[variant.product.pk]))

    # An inline formset writes rows directly, so an editable stock field here is an
    # absolute write with no lock, which discards a concurrent checkout's decrement.
    assert b'name="variants-0-stock_quantity"' not in response.content


def test_adjust_stock_sets_the_counted_total(admin_client):
    variant = ProductVariantFactory.create(stock_quantity=5)

    admin_client.post(
        reverse("admin:catalog_productvariant_changelist"),
        {
            "action": "adjust_stock",
            ACTION_CHECKBOX_NAME: [str(variant.pk)],
            "apply": "1",
            "quantity": "42",
        },
        follow=True,
    )

    variant.refresh_from_db()
    assert variant.stock_quantity == 42


# transaction=True, overriding the module marker: the other thread runs on its own
# connection and cannot see data held in an uncommitted test transaction.
@pytest.mark.django_db(transaction=True)
def test_a_restock_and_a_sale_do_not_interleave():
    from apps.catalog.services import decrement_variant_stock, set_variant_stock

    product = ProductFactory.create(is_published=True)
    variant = ProductVariantFactory.create(product=product, stock_quantity=10)

    start = threading.Barrier(2)

    def sell() -> None:
        try:
            start.wait(timeout=10)
            decrement_variant_stock(quantities={variant.pk: 3})
        finally:
            connections.close_all()

    def restock() -> None:
        try:
            start.wait(timeout=10)
            set_variant_stock(variant=variant, quantity=50)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=sell), threading.Thread(target=restock)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    variant.refresh_from_db()
    # The two writes serialised: 47 if the sale went first, 50 if the restock did.
    # 10 would mean both wrote from the same starting value.
    assert variant.stock_quantity in (47, 50)


@pytest.mark.parametrize(
    "url_name",
    [
        "admin:catalog_size_changelist",
        "admin:catalog_shade_changelist",
        "admin:catalog_category_changelist",
        "admin:catalog_product_changelist",
        "admin:catalog_productvariant_changelist",
        "admin:catalog_productimage_changelist",
    ],
)
def test_every_catalogue_changelist_renders(admin_client, url_name):
    # A changelist fails at render time -- a bad list_display name, a filter on a
    # field that does not exist -- and nothing else in the suite would notice.
    ProductVariantFactory.create()

    assert admin_client.get(reverse(url_name)).status_code == 200


def test_generating_with_no_shade_creates_shadeless_variants(admin_client):
    product = ProductFactory.create(slug="rose-water-toner")
    sizes = [SizeFactory.create(slug=slug, name=slug) for slug in ("100-ml", "200-ml")]

    _generate(admin_client, product, sizes, [])

    assert product.variants.filter(shade__isnull=True).count() == 2
    assert set(product.variants.values_list("sku", flat=True)) == {
        "ROSE-WATER-TONER-100-ML",
        "ROSE-WATER-TONER-200-ML",
    }


def _act(admin_client, action, products):
    return admin_client.post(
        reverse("admin:catalog_product_changelist"),
        {"action": action, ACTION_CHECKBOX_NAME: [str(product.pk) for product in products]},
        follow=True,
    )


def test_publish_action_publishes_only_products_with_variants(admin_client):
    ready = ProductVariantFactory.create(product__is_published=False).product
    empty = ProductFactory.create(is_published=False)

    response = _act(admin_client, "publish", [ready, empty])

    ready.refresh_from_db()
    empty.refresh_from_db()
    assert (ready.is_published, empty.is_published) == (True, False)
    messages = [str(message) for message in response.context["messages"]]
    assert any("Could not publish" in message for message in messages)


def test_unpublish_action(admin_client):
    product = ProductVariantFactory.create(product__is_published=True).product

    _act(admin_client, "unpublish", [product])

    product.refresh_from_db()
    assert product.is_published is False


def test_is_published_is_not_a_form_field(admin_client):
    product = ProductFactory.create()

    response = admin_client.get(reverse("admin:catalog_product_change", args=[product.pk]))

    assert b'name="is_published"' not in response.content


def test_make_primary_action_demotes_the_old_primary(admin_client):
    product = ProductFactory.create()
    old = ProductImageFactory.create(product=product, is_primary=True)
    new = ProductImageFactory.create(product=product, is_primary=False)

    admin_client.post(
        reverse("admin:catalog_productimage_changelist"),
        {"action": "make_primary", ACTION_CHECKBOX_NAME: [str(new.pk)]},
        follow=True,
    )

    old.refresh_from_db()
    new.refresh_from_db()
    assert (old.is_primary, new.is_primary) == (False, True)
