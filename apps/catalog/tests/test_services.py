import threading
import uuid
from decimal import Decimal

import pytest
from django.db import connections, transaction

from apps.catalog.exceptions import InsufficientStock, VariantUnavailable
from apps.catalog.models import ProductVariant
from apps.catalog.services import decrement_variant_stock, restore_variant_stock
from apps.catalog.tests.factories import ProductFactory, ProductVariantFactory


@pytest.mark.django_db
def test_decrement_variant_stock_reduces_quantity():
    product = ProductFactory(is_published=True)
    variant = ProductVariantFactory(product=product, stock_quantity=10)

    decrement_variant_stock(quantities={variant.pk: 3})

    variant.refresh_from_db()
    assert variant.stock_quantity == 7


@pytest.mark.django_db
def test_decrement_returns_locked_variants_for_price_resolution():
    product = ProductFactory(is_published=True, base_price=Decimal("4500.00"))
    variant = ProductVariantFactory(product=product, stock_quantity=5)

    locked = decrement_variant_stock(quantities={variant.pk: 1})

    assert locked[variant.pk].price == Decimal("4500.00")


@pytest.mark.django_db
def test_decrement_beyond_available_raises_insufficient_stock():
    product = ProductFactory(is_published=True)
    variant = ProductVariantFactory(product=product, stock_quantity=2)

    with pytest.raises(InsufficientStock) as exc_info:
        decrement_variant_stock(quantities={variant.pk: 3})

    details = exc_info.value.details
    assert details["variant_id"] == str(variant.pk)
    assert details["requested"] == 3
    # Checkout is public, so the remaining count must never reach the client.
    assert "available" not in details
    variant.refresh_from_db()
    assert variant.stock_quantity == 2


@pytest.mark.django_db
def test_decrement_is_all_or_nothing_across_the_cart():
    product = ProductFactory(is_published=True)
    plenty = ProductVariantFactory(product=product, stock_quantity=10)
    scarce = ProductVariantFactory(product=product, stock_quantity=1)

    with pytest.raises(InsufficientStock):
        decrement_variant_stock(quantities={plenty.pk: 1, scarce.pk: 5})

    plenty.refresh_from_db()
    assert plenty.stock_quantity == 10


@pytest.mark.django_db
def test_decrement_unknown_variant_raises_variant_unavailable():
    unknown = uuid.uuid4()

    with pytest.raises(VariantUnavailable) as exc_info:
        decrement_variant_stock(quantities={unknown: 1})

    assert exc_info.value.details["variant_ids"] == [str(unknown)]


@pytest.mark.django_db
def test_decrement_unpublished_variant_raises_variant_unavailable():
    product = ProductFactory(is_published=False)
    variant = ProductVariantFactory(product=product, stock_quantity=5)

    with pytest.raises(VariantUnavailable):
        decrement_variant_stock(quantities={variant.pk: 1})

    variant.refresh_from_db()
    assert variant.stock_quantity == 5


@pytest.mark.django_db
def test_restore_variant_stock_returns_quantity():
    product = ProductFactory(is_published=True)
    variant = ProductVariantFactory(product=product, stock_quantity=4)

    restore_variant_stock(quantities={variant.pk: 3})

    variant.refresh_from_db()
    assert variant.stock_quantity == 7


@pytest.mark.django_db
def test_restore_variant_stock_ignores_publication_state():
    product = ProductFactory(is_published=False)
    variant = ProductVariantFactory(product=product, stock_quantity=0)

    restore_variant_stock(quantities={variant.pk: 2})

    variant.refresh_from_db()
    assert variant.stock_quantity == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_decrement_does_not_oversell():
    product = ProductFactory(is_published=True)
    variant = ProductVariantFactory(product=product, stock_quantity=1)

    start = threading.Barrier(2)
    failures: list[Exception] = []

    def buy_the_last_unit() -> None:
        try:
            start.wait(timeout=10)
            with transaction.atomic():
                decrement_variant_stock(quantities={variant.pk: 1})
        except Exception as exc:  # noqa: BLE001 - the race's loser is the assertion
            failures.append(exc)
        finally:
            # Each thread opens its own connection. Leaving one open holds a
            # session on the test database and makes its teardown fail.
            connections.close_all()

    buyers = [threading.Thread(target=buy_the_last_unit) for _ in range(2)]
    for buyer in buyers:
        buyer.start()
    for buyer in buyers:
        buyer.join(timeout=30)

    variant.refresh_from_db()
    assert variant.stock_quantity == 0
    assert [type(failure) for failure in failures] == [InsufficientStock]
    assert ProductVariant.objects.filter(pk=variant.pk, stock_quantity__lt=0).count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", [0, -3])
def test_non_positive_quantity_is_rejected_before_any_write(quantity):
    product = ProductFactory(is_published=True)
    variant = ProductVariantFactory(product=product, stock_quantity=5)

    with pytest.raises(ValueError, match="positive"):
        decrement_variant_stock(quantities={variant.pk: quantity})

    variant.refresh_from_db()
    assert variant.stock_quantity == 5


@pytest.mark.django_db
def test_restore_also_rejects_a_non_positive_quantity():
    product = ProductFactory(is_published=True)
    variant = ProductVariantFactory(product=product, stock_quantity=5)

    with pytest.raises(ValueError, match="positive"):
        restore_variant_stock(quantities={variant.pk: -2})

    variant.refresh_from_db()
    assert variant.stock_quantity == 5
