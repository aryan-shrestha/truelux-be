"""Populate a development order history.

`seed_demo` gives a developer a catalogue; this gives them orders against it, in
every state the admin has an action for. Without it `OrderAdmin` and `PaymentAdmin`
are empty pages, and the three standing duties in `docs/handover.md` -- release
held stock, verify a stranded payment, resend a failed email -- cannot be practised
against anything.

Every order is placed through `place_order` and moved by the same transition
services the admin calls, so the stock arithmetic, the order numbers and the
payment rows are the ones the application would really produce. The single
exception is the Khalti payment row, which is written directly: `initiate_khalti_payment`
makes an HTTP request, and a seed command must not reach the network.
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
from apps.payments.models import Payment, PaymentStatus
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
    # Khalti only. False leaves the payment pending, as an abandoned redirect does.
    payment_completed: bool = True
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
    # The failure mode ADR 0004 accepts: the customer reached Khalti and never came
    # back, and this order holds its stock until a human cancels it. The pending
    # Khalti payment is what "Verify selected payments with Khalti" is for.
    OrderSpec(
        full_name="Bikash Thapa",
        city="Lalitpur",
        district="Lalitpur",
        payment_method=PaymentMethod.KHALTI,
        lines=((1, 2),),
        status=OrderStatus.PENDING,
        payment_completed=False,
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
        payment_method=PaymentMethod.KHALTI,
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
        payment_method=PaymentMethod.KHALTI,
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
            "One Khalti order is deliberately unpaid and still holding its stock, "
            "which is what the admin's verify action exists for. The confirmation "
            "emails above are the console backend working, not an error."
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

        if spec.payment_method == PaymentMethod.KHALTI:
            self._advance_khalti(order, spec)
        else:
            self._advance_cod(order, spec)

        # complete_cod_payment marks the order paid through its own locked
        # instance, so this one is a status behind and the next transition would
        # refuse. Refreshed for both methods rather than only the one that needs
        # it, so the difference cannot become a trap later.
        order.refresh_from_db()

        if spec.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            mark_order_shipped(order=order)
        if spec.status == OrderStatus.DELIVERED:
            mark_order_delivered(order=order)
        if spec.status == OrderStatus.CANCELLED:
            cancel_order(order=order)

        return order

    def _advance_cod(self, order: Order, spec: OrderSpec) -> None:
        payment = record_cod_payment(order=order)
        if spec.status != OrderStatus.PENDING and spec.status != OrderStatus.CANCELLED:
            # The service the merchant's "Mark cash as collected" action calls. It
            # marks the order paid too, which is why nothing here calls
            # mark_order_paid for a cash order.
            complete_cod_payment(payment=payment)

    def _advance_khalti(self, order: Order, spec: OrderSpec) -> None:
        # Written directly rather than through initiate_khalti_payment, which makes
        # an HTTP request. The shape matches what that service records, plus what
        # verify_khalti_payment adds on a Completed lookup.
        completed = spec.payment_completed and spec.status != OrderStatus.PENDING
        Payment.objects.create(
            order=order,
            method=PaymentMethod.KHALTI,
            status=PaymentStatus.COMPLETED if completed else PaymentStatus.PENDING,
            amount=order.total,
            pidx=f"seed-pidx-{order.order_number}",
            transaction_id=f"seed-txn-{order.order_number}" if completed else "",
            raw_status="Completed" if completed else "",
        )
        if completed:
            mark_order_paid(order=order)
