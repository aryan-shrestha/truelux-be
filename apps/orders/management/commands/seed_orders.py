"""Populate a development order history.

`seed_demo` gives a developer a catalogue; this gives them orders against it, in
every state the admin has an action for. Without it `OrderAdmin` and `PaymentAdmin`
are empty pages.

Every order is placed through `place_order` and moved by the same transition
services the admin calls, so the stock arithmetic, the order numbers and the
payment rows are the ones the application would really produce.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.catalog.models import ProductVariant
from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.models import Order
from apps.orders.services import (
    cancel_order,
    mark_order_delivered,
    mark_order_paid,
    mark_order_shipped,
    place_order,
)
from apps.payments.models import Payment
from apps.payments.services import complete_cod_payment, record_cod_payment

# Every seeded order carries an address at this domain, and `--flush` deletes by it.
# `.invalid` is reserved by RFC 2606 and can never resolve, so a seeded confirmation
# cannot reach a real inbox even if a developer points the seed at a real SMTP relay.
SEED_EMAIL_DOMAIN = "seed.invalid"


@dataclass(frozen=True)
class OrderSpec:
    full_name: str
    city: str
    district: str
    payment_method: str
    # (index into the available variants, quantity). Indexes rather than SKUs so
    # this does not couple to seed_demo's catalogue.
    lines: tuple[tuple[int, int], ...]
    status: str
    note: str = ""


ORDERS: tuple[OrderSpec, ...] = (
    OrderSpec(
        full_name="Asha Rai",
        city="Kathmandu",
        district="Kathmandu",
        payment_method=PaymentMethod.COD,
        lines=((0, 1),),
        status=OrderStatus.PENDING,
        note="Leave with the neighbour if I am out.",
    ),
    OrderSpec(
        full_name="Bikash Thapa",
        city="Lalitpur",
        district="Lalitpur",
        payment_method=PaymentMethod.COD,
        lines=((1, 2),),
        status=OrderStatus.PENDING,
    ),
    OrderSpec(
        full_name="Chhiring Sherpa",
        city="Pokhara",
        district="Kaski",
        payment_method=PaymentMethod.COD,
        lines=((2, 1), (3, 1)),
        status=OrderStatus.PAID,
    ),
    OrderSpec(
        full_name="Deepa Gurung",
        city="Bhaktapur",
        district="Bhaktapur",
        payment_method=PaymentMethod.COD,
        lines=((4, 3),),
        status=OrderStatus.PAID,
    ),
    OrderSpec(
        full_name="Eliza Magar",
        city="Kathmandu",
        district="Kathmandu",
        payment_method=PaymentMethod.COD,
        lines=((5, 1),),
        status=OrderStatus.SHIPPED,
    ),
    OrderSpec(
        full_name="Furba Tamang",
        city="Biratnagar",
        district="Morang",
        payment_method=PaymentMethod.COD,
        lines=((6, 1), (7, 2)),
        status=OrderStatus.DELIVERED,
    ),
    # Cancelled after placement, so its stock went out and came back. The variant
    # counts only add up if `cancel_order` did its job.
    OrderSpec(
        full_name="Gita Shrestha",
        city="Kathmandu",
        district="Kathmandu",
        payment_method=PaymentMethod.COD,
        lines=((8, 1),),
        status=OrderStatus.CANCELLED,
    ),
)


class Command(BaseCommand):
    help = "Populate a development order history. Refuses to run outside DEBUG."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete the orders this command created before seeding again.",
        )
        parser.add_argument(
            "--flush-only",
            action="store_true",
            help="Delete the orders this command created and stop, releasing the catalogue.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # The same refusal seed_demo makes, for the same reason: a mistyped
        # DJANGO_SETTINGS_MODULE must not put invented orders in a real shop.
        if not settings.DEBUG:
            raise CommandError("seed_orders writes demo rows and only runs with DEBUG enabled.")

        if options["flush"] or options["flush_only"]:
            self._flush()

        # Deleting without reseeding is what lets `seed_demo --flush` run at all:
        # OrderItem.variant is PROTECT, so the catalogue cannot be replaced while
        # any seeded order references it. `make reseed` uses this.
        if options["flush_only"]:
            return

        variants = self._available_variants()

        with transaction.atomic():
            placed = [self._seed_order(spec, variants) for spec in ORDERS]

        # Counted from the database, not from the objects above: the transition
        # services refetch under a lock, so an object handed to one of them is a
        # status behind whatever it did.
        by_status = Counter(
            Order.objects.filter(pk__in=[order.pk for order in placed]).values_list(
                "status", flat=True
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(placed)} orders: "
                + ", ".join(
                    f"{by_status[status]} {status}"
                    for status in OrderStatus.values
                    if by_status[status]
                )
            )
        )
        self.stdout.write(
            "The confirmation emails above are the console backend working, not an error."
        )

    def _flush(self) -> None:
        # Payments before orders: Payment.order is PROTECT, so the orders cannot go
        # first. Catalogue rows are left alone -- OrderItem.variant is PROTECT too,
        # which is why `seed_demo --flush` needs this command to have run first.
        seeded = Order.objects.filter(email__endswith=f"@{SEED_EMAIL_DOMAIN}")
        _, payments = Payment.objects.filter(order__in=seeded).delete()
        _, orders = seeded.delete()
        self.stdout.write(
            f"Flushed {orders.get('orders.Order', 0)} orders, "
            f"{orders.get('orders.OrderItem', 0)} order items and "
            f"{payments.get('payments.Payment', 0)} payments. "
            "Their stock is not returned -- cancel an order for that."
        )

    def _available_variants(self) -> list[ProductVariant]:
        # Ordered by sku so a reseed picks the same variants and the seeded history
        # is reproducible. Published only: placing an order against an unpublished
        # variant is exactly what `place_order` refuses.
        variants = list(
            ProductVariant.objects.filter(product__is_published=True, stock_quantity__gte=3)
            .select_related("product")
            .order_by("sku")
        )
        needed = max(index for spec in ORDERS for index, _ in spec.lines) + 1
        if len(variants) < needed:
            raise CommandError(
                f"Need {needed} published variants with stock; found {len(variants)}. "
                "Run `manage.py seed_demo` first."
            )
        return variants

    def _seed_order(self, spec: OrderSpec, variants: list[ProductVariant]) -> Order:
        order = place_order(
            items=[
                {"variant_id": variants[index].pk, "quantity": quantity}
                for index, quantity in spec.lines
            ],
            email=f"{spec.full_name.split()[0].lower()}@{SEED_EMAIL_DOMAIN}",
            phone="9800000000",
            full_name=spec.full_name,
            address_line="1 Demo Road",
            city=spec.city,
            district=spec.district,
            payment_method=spec.payment_method,
            note=spec.note,
        )

        payment = record_cod_payment(order=order)

        if spec.status in (OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            mark_order_paid(order=order)
        if spec.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            mark_order_shipped(order=order)
        if spec.status == OrderStatus.DELIVERED:
            mark_order_delivered(order=order)
            complete_cod_payment(payment=payment)
        if spec.status == OrderStatus.CANCELLED:
            cancel_order(order=order)

        return order
