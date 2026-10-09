import pytest
from django.db import IntegrityError

from apps.catalog.models import ProductVariant
from apps.catalog.services import create_variant, delete_variant
from apps.catalog.tests.factories import ProductFactory, ProductVariantFactory, SizeFactory
from apps.inventory.exceptions import InvalidStockAdjustment
from apps.inventory.models import MovementReason, StockMovement
from apps.inventory.services import (
    adjust_variant_stock,
    decrement_variant_stock,
    set_variant_stock,
)
from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.services import cancel_order, place_order
from apps.orders.tests.factories import OrderFactory, OrderItemFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_a_sale_records_a_movement_per_variant_against_the_order():
    product = ProductFactory.create(is_published=True)
    first = ProductVariantFactory.create(product=product, stock_quantity=10)
    second = ProductVariantFactory.create(product=product, stock_quantity=4)
    order = OrderFactory.create()

    decrement_variant_stock(quantities={first.pk: 3, second.pk: 1}, order_id=order.pk)

    movements = {m.variant_id: m for m in StockMovement.objects.all()}
    assert {pk: (m.quantity_change, m.balance_after) for pk, m in movements.items()} == {
        first.pk: (-3, 7),
        second.pk: (-1, 3),
    }
    assert all(m.reason == MovementReason.SALE for m in movements.values())
    assert all(m.order_id == order.pk and m.actor is None for m in movements.values())


def test_cancelling_records_who_returned_the_stock():
    staff = UserFactory.create(is_staff=True)
    variant = ProductVariantFactory.create(stock_quantity=1)
    order = OrderFactory.create(status=OrderStatus.PENDING)
    OrderItemFactory.create(order=order, variant=variant, quantity=2)

    cancel_order(order=order, actor=staff)

    movement = StockMovement.objects.get()
    assert movement.reason == MovementReason.CANCELLATION
    assert (movement.quantity_change, movement.balance_after) == (2, 3)
    assert movement.order_id == order.pk
    assert movement.actor == staff


def test_a_stocktake_records_the_variance_from_the_replaced_count():
    staff = UserFactory.create(is_staff=True)
    variant = ProductVariantFactory.create(stock_quantity=10)

    set_variant_stock(variant=variant, quantity=6, actor=staff, note="Shelf count")

    movement = StockMovement.objects.get()
    assert movement.reason == MovementReason.STOCKTAKE
    assert (movement.quantity_change, movement.balance_after) == (-4, 6)
    assert (movement.actor, movement.note, movement.sku) == (staff, "Shelf count", variant.sku)


def test_a_stocktake_that_confirms_the_count_is_still_recorded():
    variant = ProductVariantFactory.create(stock_quantity=5)

    set_variant_stock(variant=variant, quantity=5, actor=None)

    assert StockMovement.objects.get().quantity_change == 0


def test_an_adjustment_is_relative_so_it_keeps_a_sale_made_meanwhile():
    product = ProductFactory.create(is_published=True)
    variant = ProductVariantFactory.create(product=product, stock_quantity=10)
    stale = ProductVariant.objects.get(pk=variant.pk)

    decrement_variant_stock(quantities={variant.pk: 3}, order_id=OrderFactory.create().pk)
    movement = adjust_variant_stock(
        variant=stale, quantity_change=5, reason=MovementReason.RECEIVED, actor=None
    )

    variant.refresh_from_db()
    assert variant.stock_quantity == 12
    assert (movement.quantity_change, movement.balance_after) == (5, 12)


@pytest.mark.parametrize(
    ("reason", "change"),
    [
        (MovementReason.RECEIVED, -2),
        (MovementReason.RETURNED, -1),
        (MovementReason.DAMAGED, 2),
        (MovementReason.TESTER, 1),
        (MovementReason.CORRECTION, 0),
    ],
)
def test_an_adjustment_must_move_stock_the_way_its_reason_says(reason, change):
    variant = ProductVariantFactory.create(stock_quantity=5)

    with pytest.raises(InvalidStockAdjustment) as exc_info:
        adjust_variant_stock(variant=variant, quantity_change=change, reason=reason, actor=None)

    assert "quantity_change" in exc_info.value.details
    variant.refresh_from_db()
    assert variant.stock_quantity == 5
    assert not StockMovement.objects.exists()


def test_an_adjustment_cannot_take_stock_below_zero():
    variant = ProductVariantFactory.create(stock_quantity=2)

    with pytest.raises(InvalidStockAdjustment, match="Only 2 in stock"):
        adjust_variant_stock(
            variant=variant, quantity_change=-3, reason=MovementReason.DAMAGED, actor=None
        )

    variant.refresh_from_db()
    assert variant.stock_quantity == 2
    assert not StockMovement.objects.exists()


def test_a_correction_may_go_either_way():
    variant = ProductVariantFactory.create(stock_quantity=5)

    adjust_variant_stock(
        variant=variant, quantity_change=-1, reason=MovementReason.CORRECTION, actor=None
    )
    adjust_variant_stock(
        variant=variant, quantity_change=3, reason=MovementReason.CORRECTION, actor=None
    )

    variant.refresh_from_db()
    assert variant.stock_quantity == 7


def test_order_reasons_are_not_manual_adjustments():
    variant = ProductVariantFactory.create(stock_quantity=5)

    with pytest.raises(ValueError, match="not a manual adjustment"):
        adjust_variant_stock(
            variant=variant, quantity_change=-1, reason=MovementReason.SALE, actor=None
        )


def test_opening_stock_is_recorded_as_a_stocktake():
    staff = UserFactory.create(is_staff=True)

    variant = create_variant(
        product=ProductFactory.create(),
        fields={"sku": "OPEN-1", "size": SizeFactory.create()},
        actor=staff,
        stock_quantity=7,
    )

    movement = StockMovement.objects.get()
    assert variant.stock_quantity == 7
    assert movement.reason == MovementReason.STOCKTAKE
    assert (movement.quantity_change, movement.balance_after, movement.actor) == (7, 7, staff)


def test_a_variant_created_without_stock_records_nothing():
    create_variant(
        product=ProductFactory.create(),
        fields={"sku": "EMPTY-1", "size": SizeFactory.create()},
        actor=None,
    )

    assert not StockMovement.objects.exists()


def test_history_survives_deleting_the_variant():
    variant = ProductVariantFactory.create(stock_quantity=0)
    set_variant_stock(variant=variant, quantity=4, actor=None)

    delete_variant(variant=variant)

    movement = StockMovement.objects.get()
    assert movement.variant is None
    assert (movement.sku, movement.balance_after) == (variant.sku, 4)


def test_the_database_refuses_a_movement_against_its_reason():
    variant = ProductVariantFactory.create()

    with pytest.raises(IntegrityError):
        StockMovement.objects.create(
            variant=variant,
            sku=variant.sku,
            reason=MovementReason.DAMAGED,
            quantity_change=2,
            balance_after=2,
        )


def test_placing_an_order_records_its_sales_against_that_order(shipping_settings):
    variant = ProductVariantFactory.create(
        product=ProductFactory.create(is_published=True), stock_quantity=5
    )

    order = place_order(
        items=[{"variant_id": variant.pk, "quantity": 2}],
        email="buyer@example.com",
        phone="9800000000",
        full_name="Buyer",
        address_line="1 Test Road",
        city="Kathmandu",
        district="Kathmandu",
        payment_method=PaymentMethod.COD,
    )

    movement = StockMovement.objects.get()
    assert movement.order == order
    assert (movement.reason, movement.quantity_change, movement.balance_after) == (
        MovementReason.SALE,
        -2,
        3,
    )
