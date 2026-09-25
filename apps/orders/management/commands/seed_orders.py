"""Populate a development order history across the last month, in every status.

Every order is placed through `place_order` and moved by the same transition
services the admin API calls, so stock, order numbers and payment rows are the
ones the application would produce. Only `created_at` is rewritten afterwards,
because the admin dashboard's revenue and sales-by-day need a history.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.models import Order
from apps.orders.services import place_order, transition_order
from apps.payments.models import Payment
from apps.payments.services import complete_cod_payment, record_cod_payment

# `--flush` deletes by this domain. `.invalid` (RFC 2606) can never resolve, so a
# seeded confirmation cannot reach a real inbox even through a real SMTP relay.
SEED_EMAIL_DOMAIN = "seed.invalid"

_PATH_TO: dict[str, tuple[str, ...]] = {
    OrderStatus.PENDING: (),
    OrderStatus.CONFIRMED: (OrderStatus.CONFIRMED,),
    OrderStatus.SHIPPED: (OrderStatus.CONFIRMED, OrderStatus.SHIPPED),
    OrderStatus.DELIVERED: (OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.DELIVERED),
    OrderStatus.CANCELLED: (OrderStatus.CANCELLED,),
}


@dataclass(frozen=True)
class OrderSpec:
    full_name: str
    city: str
    district: str
    # (index into the available variants, quantity): indexes rather than SKUs so this
    # does not couple to seed_demo's catalogue.
    lines: tuple[tuple[int, int], ...]
    status: str
    days_ago: int
    note: str = ""


ORDERS: tuple[OrderSpec, ...] = (
    OrderSpec(
        "Asha Rai",
        "Kathmandu",
        "Kathmandu",
        ((0, 1),),
        OrderStatus.PENDING,
        0,
        "Leave with the neighbour if I am out.",
    ),
    OrderSpec("Bikash Thapa", "Lalitpur", "Lalitpur", ((1, 2),), OrderStatus.PENDING, 0),
    OrderSpec("Chhiring Sherpa", "Pokhara", "Kaski", ((2, 1), (3, 1)), OrderStatus.CONFIRMED, 1),
    OrderSpec("Deepa Gurung", "Bhaktapur", "Bhaktapur", ((4, 1),), OrderStatus.CONFIRMED, 2),
    OrderSpec("Eliza Magar", "Kathmandu", "Kathmandu", ((5, 1),), OrderStatus.SHIPPED, 3),
    OrderSpec("Furba Tamang", "Biratnagar", "Morang", ((6, 1), (7, 1)), OrderStatus.SHIPPED, 4),
    OrderSpec("Gita Shrestha", "Kathmandu", "Kathmandu", ((8, 1),), OrderStatus.CANCELLED, 5),
    OrderSpec("Hari Karki", "Butwal", "Rupandehi", ((9, 1),), OrderStatus.DELIVERED, 6),
    OrderSpec("Isha Joshi", "Lalitpur", "Lalitpur", ((10, 2),), OrderStatus.DELIVERED, 8),
    OrderSpec(
        "Jamuna Adhikari", "Dharan", "Sunsari", ((11, 1), (12, 1)), OrderStatus.DELIVERED, 10
    ),
    OrderSpec("Kiran Basnet", "Kathmandu", "Kathmandu", ((13, 1),), OrderStatus.DELIVERED, 12),
    OrderSpec("Laxmi Poudel", "Chitwan", "Chitwan", ((14, 1),), OrderStatus.CANCELLED, 14),
    OrderSpec("Maya Lama", "Bhaktapur", "Bhaktapur", ((15, 1), (0, 1)), OrderStatus.DELIVERED, 16),
    OrderSpec("Nabin KC", "Pokhara", "Kaski", ((16, 1),), OrderStatus.DELIVERED, 19),
    OrderSpec("Ojaswi Bhandari", "Kathmandu", "Kathmandu", ((17, 1),), OrderStatus.DELIVERED, 22),
    OrderSpec("Pratima Rana", "Hetauda", "Makwanpur", ((18, 2),), OrderStatus.DELIVERED, 25),
    OrderSpec("Rojina Maharjan", "Lalitpur", "Lalitpur", ((19, 1),), OrderStatus.DELIVERED, 28),
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
        # Ordered by sku so a reseed picks the same variants. Only variants the
        # storefront could sell, since that is all place_order accepts.
        variants = list(
            ProductVariant.objects.filter(
                product__is_published=True,
                product__brand__is_active=True,
                stock_quantity__gte=3,
            ).order_by("sku")
        )
        needed = max(index for spec in ORDERS for index, _ in spec.lines) + 1
        if len(variants) < needed:
            raise CommandError(
                f"Need {needed} published variants with stock; found {len(variants)}. "
                "Run `manage.py seed_demo` first."
            )
        return variants

    def _seed_order(self, spec: OrderSpec, variants: list[ProductVariant]) -> Order:
        first_name = spec.full_name.split()[0].lower()
        order = place_order(
            items=[
                {"variant_id": variants[index].pk, "quantity": quantity}
                for index, quantity in spec.lines
            ],
            email=f"{first_name}@{SEED_EMAIL_DOMAIN}",
            phone="9800000000",
            full_name=spec.full_name,
            address_line="1 Demo Road",
            city=spec.city,
            district=spec.district,
            payment_method=PaymentMethod.COD,
            note=spec.note,
        )
        payment = record_cod_payment(order=order)

        for status in _PATH_TO[spec.status]:
            order = transition_order(order=order, to=status)
        if spec.status == OrderStatus.DELIVERED:
            complete_cod_payment(payment=payment)

        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=spec.days_ago, hours=len(first_name))
        )
        return order
