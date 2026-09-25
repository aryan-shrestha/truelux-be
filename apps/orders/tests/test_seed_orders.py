from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import Product, ProductVariant
from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.management.commands.seed_orders import ORDERS, SEED_EMAIL_DOMAIN
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment, PaymentStatus


@pytest.fixture
def seeded(db, settings, tmp_path):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo")
    call_command("seed_orders")


def _seeded_orders():
    return Order.objects.filter(email__endswith=f"@{SEED_EMAIL_DOMAIN}")


@pytest.mark.django_db
def test_seeding_outside_debug_is_refused(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_orders")

    assert not Order.objects.exists()


@pytest.mark.django_db
def test_seeding_without_a_catalogue_says_which_command_to_run_first(settings):
    settings.DEBUG = True

    with pytest.raises(CommandError, match="seed_demo"):
        call_command("seed_orders")


@pytest.mark.django_db
def test_seed_covers_every_order_status(seeded):
    # The admin has an action per transition, and an empty changelist exercises
    # none of them. Every status present means every action has something to act on.
    seeded_statuses = set(_seeded_orders().values_list("status", flat=True))

    assert seeded_statuses == set(OrderStatus.values)


@pytest.mark.django_db
def test_every_seeded_order_has_a_payment(seeded):
    # A payment table that does not answer "what is owed" for every order is the
    # exact failure payments.md's recording-at-placement decision exists to avoid.
    assert not _seeded_orders().filter(payments__isnull=True).exists()


@pytest.mark.django_db
def test_cash_is_collected_only_on_delivered_orders(seeded):
    payments = Payment.objects.filter(order__in=_seeded_orders())

    assert {payment.method for payment in payments} == {PaymentMethod.COD}
    completed = payments.filter(status=PaymentStatus.COMPLETED)
    assert completed.exists()
    assert not completed.exclude(order__status=OrderStatus.DELIVERED).exists()


@pytest.mark.django_db
def test_seeding_takes_stock_for_live_orders_and_gives_it_back_for_cancelled(
    db, settings, tmp_path
):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo")
    before = _total_stock()

    call_command("seed_orders")

    # Placed through place_order and cancelled through cancel_order, so this is the
    # application's own arithmetic: the catalogue is down by exactly what orders
    # still hold, and the cancelled one gave its units back.
    still_held = sum(
        item.quantity for item in OrderItem.objects.exclude(order__status=OrderStatus.CANCELLED)
    )
    assert _total_stock() == before - still_held
    assert OrderItem.objects.filter(order__status=OrderStatus.CANCELLED).exists()


def _total_stock() -> int:
    return sum(ProductVariant.objects.values_list("stock_quantity", flat=True))


@pytest.mark.django_db
def test_flush_removes_the_orders_and_their_payments(seeded):
    # --flush deletes and seeds again, so one generation survives rather than two.
    call_command("seed_orders", "--flush")

    assert _seeded_orders().count() == len(ORDERS)
    assert Payment.objects.count() == len(ORDERS)


@pytest.mark.django_db
def test_flush_leaves_the_catalogue_alone(seeded):
    products = Product.objects.count()

    call_command("seed_orders", "--flush")

    assert Product.objects.count() == products


@pytest.mark.django_db
def test_flush_only_deletes_without_reseeding(seeded):
    # What makes `make reseed` possible at all: plain --flush seeds again, and
    # those new orders would PROTECT the catalogue from the very next command.
    call_command("seed_orders", "--flush-only")

    assert not _seeded_orders().exists()
    assert not Payment.objects.exists()


@pytest.mark.django_db
def test_flush_only_releases_the_catalogue_for_reseeding(seeded):
    # The `make reseed` sequence, in a test: orders go, then the catalogue can be
    # replaced, then orders come back.
    call_command("seed_orders", "--flush-only")
    call_command("seed_demo", "--flush")
    call_command("seed_orders")

    assert _seeded_orders().count() == len(ORDERS)


@pytest.mark.django_db
def test_seeded_products_cannot_be_flushed_while_orders_reference_them(seeded):
    # OrderItem.variant is PROTECT. Without the guard this is a traceback naming a
    # foreign key; with it, it names the command that releases them.
    with pytest.raises(CommandError, match="seed_orders --flush"):
        call_command("seed_demo", "--flush")


@pytest.mark.django_db
def test_seeded_orders_span_the_dashboard_window(seeded):
    dates = {order.created_at.date() for order in _seeded_orders()}

    assert len(dates) > 10
    assert max(dates) - min(dates) < timedelta(days=30)
