import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connections

from apps.catalog.tests.factories import ProductVariantFactory
from apps.orders.constants import OrderStatus
from apps.orders.exceptions import (
    InvalidStatusTransition,
    OrderAlreadyShipped,
    OrderNotCancellable,
)
from apps.orders.services import (
    cancel_order,
    confirm_order,
    generate_order_number,
    mark_order_delivered,
    mark_order_shipped,
)
from apps.orders.tests.factories import OrderFactory, OrderItemFactory

pytestmark = pytest.mark.django_db


def test_order_number_has_the_documented_shape():
    number = generate_order_number()

    assert re.fullmatch(r"TL-\d{4}-\d{6}", number)


def test_order_numbers_are_unique_under_concurrency():
    def reserve():
        try:
            return generate_order_number()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        numbers = list(pool.map(lambda _: reserve(), range(8)))

    assert len(set(numbers)) == 8


def test_confirm_from_pending_succeeds():
    order = OrderFactory.create(status=OrderStatus.PENDING)

    confirm_order(order=order)

    order.refresh_from_db()
    assert order.status == OrderStatus.CONFIRMED


def test_mark_shipped_from_confirmed_succeeds():
    order = OrderFactory.create(status=OrderStatus.CONFIRMED)

    mark_order_shipped(order=order)

    order.refresh_from_db()
    assert order.status == OrderStatus.SHIPPED


def test_mark_delivered_from_shipped_succeeds():
    order = OrderFactory.create(status=OrderStatus.SHIPPED)

    mark_order_delivered(order=order)

    order.refresh_from_db()
    assert order.status == OrderStatus.DELIVERED


@pytest.mark.parametrize(
    ("transition", "status"),
    [
        (confirm_order, OrderStatus.SHIPPED),
        (confirm_order, OrderStatus.CANCELLED),
        (mark_order_shipped, OrderStatus.PENDING),
        (mark_order_shipped, OrderStatus.DELIVERED),
        (mark_order_delivered, OrderStatus.PENDING),
        (mark_order_delivered, OrderStatus.CONFIRMED),
    ],
)
def test_an_illegal_transition_raises_and_leaves_the_status_alone(transition, status):
    order = OrderFactory.create(status=status)

    with pytest.raises(InvalidStatusTransition):
        transition(order=order)

    order.refresh_from_db()
    assert order.status == status


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.CONFIRMED])
def test_cancelling_restores_stock(status):
    variant = ProductVariantFactory.create(stock_quantity=7)
    order = OrderFactory.create(status=status)
    OrderItemFactory.create(order=order, variant=variant, quantity=2)

    cancel_order(order=order)

    variant.refresh_from_db()
    order.refresh_from_db()
    assert variant.stock_quantity == 9
    assert order.status == OrderStatus.CANCELLED


def test_cancelling_sums_repeated_variants_before_restoring():
    variant = ProductVariantFactory.create(stock_quantity=0)
    order = OrderFactory.create(status=OrderStatus.PENDING)
    OrderItemFactory.create(order=order, variant=variant, quantity=2)
    OrderItemFactory.create(order=order, variant=variant, quantity=3)

    cancel_order(order=order)

    variant.refresh_from_db()
    assert variant.stock_quantity == 5


@pytest.mark.parametrize("status", [OrderStatus.SHIPPED, OrderStatus.DELIVERED])
def test_cancel_after_shipping_raises_and_restores_nothing(status):
    variant = ProductVariantFactory.create(stock_quantity=4)
    order = OrderFactory.create(status=status)
    OrderItemFactory.create(order=order, variant=variant, quantity=2)

    with pytest.raises(OrderAlreadyShipped):
        cancel_order(order=order)

    variant.refresh_from_db()
    order.refresh_from_db()
    assert variant.stock_quantity == 4
    assert order.status == status


def test_cancelling_an_already_cancelled_order_does_not_restore_stock_twice():
    variant = ProductVariantFactory.create(stock_quantity=4)
    order = OrderFactory.create(status=OrderStatus.CANCELLED)
    OrderItemFactory.create(order=order, variant=variant, quantity=2)

    with pytest.raises(OrderNotCancellable):
        cancel_order(order=order)

    variant.refresh_from_db()
    assert variant.stock_quantity == 4


# transaction=True, overriding the module marker: the other thread runs on its own
# connection and cannot see data held in an uncommitted test transaction.
@pytest.mark.django_db(transaction=True)
def test_concurrent_cancellation_restores_the_stock_only_once():
    variant = ProductVariantFactory.create(stock_quantity=0)
    order = OrderFactory.create(status=OrderStatus.PENDING)
    OrderItemFactory.create(order=order, variant=variant, quantity=3)

    start = threading.Barrier(2)
    failures: list[Exception] = []

    def cancel_it() -> None:
        try:
            start.wait(timeout=10)
            cancel_order(order=order)
        except Exception as exc:  # noqa: BLE001 - the race's loser is the assertion
            failures.append(exc)
        finally:
            # Each thread opens its own connection. Leaving one open holds a
            # session on the test database and makes its teardown fail.
            connections.close_all()

    cancellers = [threading.Thread(target=cancel_it) for _ in range(2)]
    for canceller in cancellers:
        canceller.start()
    for canceller in cancellers:
        canceller.join(timeout=30)

    variant.refresh_from_db()
    assert variant.stock_quantity == 3
    assert [type(failure) for failure in failures] == [OrderNotCancellable]
