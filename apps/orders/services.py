from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.services import decrement_variant_stock, restore_variant_stock
from apps.core.logging import get_logger
from apps.orders.constants import (
    ORDER_NUMBER_DIGITS,
    ORDER_NUMBER_PREFIX,
    ORDER_NUMBER_SEQUENCE,
    OrderStatus,
)
from apps.orders.emails import send_order_confirmation, send_order_shipped
from apps.orders.exceptions import (
    EmptyCart,
    InvalidStatusTransition,
    OrderAlreadyShipped,
    OrderNotCancellable,
)
from apps.orders.models import Order, OrderItem

logger = get_logger(__name__)

_CANCELLABLE_STATUSES = (OrderStatus.PENDING, OrderStatus.PAID)
_SHIPPED_STATUSES = (OrderStatus.SHIPPED, OrderStatus.DELIVERED)


def generate_order_number() -> str:
    """Reserves the next order number from the Postgres sequence.

    The reservation is not rolled back with the surrounding transaction, so a
    failed placement leaves a gap in the series rather than reissuing a number.
    """
    with connection.cursor() as cursor:
        # A sequence name cannot be a bound parameter, so it is interpolated. It is
        # a module constant, never anything a request carries.
        cursor.execute(f"SELECT nextval('{ORDER_NUMBER_SEQUENCE}')")
        counter = cursor.fetchone()[0]

    year = timezone.now().year
    return f"{ORDER_NUMBER_PREFIX}-{year}-{counter:0{ORDER_NUMBER_DIGITS}d}"


def _transition(*, order: Order, expected: OrderStatus, new: OrderStatus, event: str) -> Order:
    if order.status != expected:
        raise InvalidStatusTransition(
            details={"order_number": order.order_number, "status": order.status}
        )

    order.status = new
    order.save(update_fields=["status", "updated_at"])

    if new == OrderStatus.SHIPPED:
        # In the service, not the admin action that calls it. If the view or the
        # action owned this, every future caller would have to remember, and the
        # one that forgot would silently ship without telling the customer --
        # which is the bug ADR 0002 keeps `status` read-only to prevent.
        transaction.on_commit(lambda: send_order_shipped(order=order))

    logger.info(event, order_id=str(order.pk), order_number=order.order_number)
    return order


def mark_order_paid(*, order: Order) -> Order:
    """Raises InvalidStatusTransition unless the order is pending."""
    return _transition(
        order=order,
        expected=OrderStatus.PENDING,
        new=OrderStatus.PAID,
        event="order.marked_paid",
    )


def mark_order_shipped(*, order: Order) -> Order:
    """Raises InvalidStatusTransition unless the order is paid."""
    return _transition(
        order=order,
        expected=OrderStatus.PAID,
        new=OrderStatus.SHIPPED,
        event="order.marked_shipped",
    )


def mark_order_delivered(*, order: Order) -> Order:
    """Raises InvalidStatusTransition unless the order has shipped."""
    return _transition(
        order=order,
        expected=OrderStatus.SHIPPED,
        new=OrderStatus.DELIVERED,
        event="order.marked_delivered",
    )


def cancel_order(*, order: Order) -> Order:
    """Raises OrderAlreadyShipped once the parcel has left, and OrderNotCancellable
    for an order that is already cancelled.

    Returns the cart's stock to the catalogue. This is the only thing that does:
    per ADR 0004 a pending order holds its stock until a human cancels it.
    """
    with transaction.atomic():
        # The status check guards a stock movement, so it is a read-then-write on
        # shared state and needs the row lock. Two staff cancelling the same order
        # at once would otherwise both pass the check and both restore the stock,
        # inflating inventory -- the same oversell ADR 0004 exists to prevent,
        # arrived at from the other side.
        locked = Order.objects.select_for_update().get(pk=order.pk)

        if locked.status in _SHIPPED_STATUSES:
            raise OrderAlreadyShipped(details={"order_number": locked.order_number})
        if locked.status not in _CANCELLABLE_STATUSES:
            raise OrderNotCancellable(
                details={"order_number": locked.order_number, "status": locked.status}
            )

        quantities: dict[UUID, int] = defaultdict(int)
        for item in locked.items.all():
            # Summed rather than assigned: nothing constrains an order to one row
            # per variant, and a second row for the same variant would otherwise
            # overwrite the first and restore too little.
            quantities[item.variant_id] += item.quantity

        restore_variant_stock(quantities=dict(quantities))

        locked.status = OrderStatus.CANCELLED
        locked.save(update_fields=["status", "updated_at"])

    logger.info(
        "order.cancelled",
        order_id=str(locked.pk),
        order_number=locked.order_number,
        variant_count=len(quantities),
    )
    return locked


def _shipping_fee_for(district: str) -> Decimal:
    if district.strip().lower() in settings.KATHMANDU_VALLEY_DISTRICTS:
        return Decimal(settings.SHIPPING_FEE_INSIDE_VALLEY)
    # An unrecognised district pays the outside-valley rate. A misspelled valley
    # district therefore overcharges, which checkout.md prefers to undercharging
    # every district the merchant has not thought of.
    return Decimal(settings.SHIPPING_FEE_OUTSIDE_VALLEY)


def place_order(
    *,
    items: Sequence[Mapping[str, Any]],
    email: str,
    phone: str,
    full_name: str,
    address_line: str,
    city: str,
    district: str,
    payment_method: str,
    note: str = "",
) -> Order:
    """Raises EmptyCart for a cart with no lines, and propagates VariantUnavailable
    and InsufficientStock from the catalogue.

    Every price is resolved from the locked rows; nothing about money is read from
    the caller.
    """
    if not items:
        raise EmptyCart()

    quantities: dict[UUID, int] = defaultdict(int)
    for item in items:
        # Two lines for one variant are one order of that many units. Assigning
        # instead of summing would decrement only the last line's quantity while
        # charging for both.
        quantities[item["variant_id"]] += item["quantity"]

    with transaction.atomic():
        # One call, whole cart. This is what owns the lock, the ascending-pk
        # ordering ADR 0004 requires, and the two availability errors. It returns
        # the locked rows, so nothing below refetches what it already holds.
        variants = decrement_variant_stock(quantities=dict(quantities))

        lines = []
        subtotal = Decimal("0.00")
        for variant_id, quantity in quantities.items():
            variant = variants[variant_id]
            unit_price = variant.price
            subtotal += unit_price * quantity
            lines.append(
                OrderItem(
                    variant=variant,
                    quantity=quantity,
                    unit_price=unit_price,
                    product_name=variant.product.name,
                    variant_size=variant.size.name,
                    variant_shade=variant.shade.name if variant.shade else "",
                    sku=variant.sku,
                )
            )

        shipping_fee = _shipping_fee_for(district)

        order = Order.objects.create(
            order_number=generate_order_number(),
            email=email,
            phone=phone,
            full_name=full_name,
            address_line=address_line,
            city=city,
            district=district,
            note=note,
            subtotal=subtotal,
            shipping_fee=shipping_fee,
            total=subtotal + shipping_fee,
            payment_method=payment_method,
        )

        for line in lines:
            line.order = order
        OrderItem.objects.bulk_create(lines)

        # on_commit, never a direct call inside atomic(): an SMTP timeout here
        # would roll back a placed order whose stock is already decremented. ADR
        # 0006 exists for this one line. It carries the access_token, which under
        # ADR 0003 is the customer's only route back to their order.
        transaction.on_commit(lambda: send_order_confirmation(order=order))

    logger.info(
        "order.placed",
        order_id=str(order.pk),
        order_number=order.order_number,
        item_count=len(lines),
        payment_method=payment_method,
    )
    return order
