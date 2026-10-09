import pytest
from django.urls import reverse

from apps.catalog.tests.factories import ProductVariantFactory
from apps.inventory.models import MovementReason, StockMovement
from apps.inventory.services import set_variant_stock
from apps.orders.constants import OrderStatus
from apps.orders.tests.factories import OrderFactory, OrderItemFactory

pytestmark = pytest.mark.django_db


def _adjust(staff_client, variant, **body):
    return staff_client.post(
        reverse("v1:admin-variant-stock-adjustments", args=[variant.pk]), body, format="json"
    )


def test_an_adjustment_changes_stock_and_returns_the_movement(staff_client):
    variant = ProductVariantFactory.create(stock_quantity=4)

    response = _adjust(
        staff_client, variant, quantity_change=6, reason="received", note="Delivery #12"
    )

    assert response.status_code == 201
    assert response.data["reason"] == "received"
    assert response.data["quantity_change"] == 6
    assert response.data["balance_after"] == 10
    assert response.data["note"] == "Delivery #12"
    actor = StockMovement.objects.get().actor
    assert actor is not None
    assert response.data["actor_email"] == actor.email
    assert response.data["order_number"] is None
    variant.refresh_from_db()
    assert variant.stock_quantity == 10


def test_a_contradictory_adjustment_is_a_field_error(staff_client):
    variant = ProductVariantFactory.create(stock_quantity=4)

    response = _adjust(staff_client, variant, quantity_change=2, reason="damaged")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert "quantity_change" in response.data["error"]["details"]


def test_order_reasons_cannot_be_posted(staff_client):
    variant = ProductVariantFactory.create(stock_quantity=4)

    response = _adjust(staff_client, variant, quantity_change=-1, reason="sale")

    assert response.status_code == 400
    assert "reason" in response.data["error"]["details"]
    assert not StockMovement.objects.exists()


def test_adjusting_an_unknown_variant_is_404(staff_client):
    response = staff_client.post(
        reverse(
            "v1:admin-variant-stock-adjustments", args=["00000000-0000-0000-0000-000000000000"]
        ),
        {"quantity_change": 1, "reason": "received"},
        format="json",
    )

    assert response.status_code == 404


def test_a_stock_patch_is_recorded_as_a_stocktake_by_the_caller(staff_client):
    variant = ProductVariantFactory.create(stock_quantity=3)

    staff_client.patch(reverse("v1:admin-variant-detail", args=[variant.pk]), {"stock_quantity": 9})

    movement = StockMovement.objects.get()
    assert movement.reason == MovementReason.STOCKTAKE
    assert movement.quantity_change == 6
    assert movement.actor is not None
    assert movement.actor.is_staff


def test_movements_list_newest_first_and_filters_by_variant(staff_client):
    variant = ProductVariantFactory.create(stock_quantity=0)
    other = ProductVariantFactory.create(stock_quantity=0)
    set_variant_stock(variant=variant, quantity=5, actor=None)
    set_variant_stock(variant=other, quantity=1, actor=None)
    set_variant_stock(variant=variant, quantity=8, actor=None)

    response = staff_client.get(
        reverse("v1:admin-stock-movement-list"), {"variant": str(variant.pk)}
    )

    assert response.status_code == 200
    assert [row["balance_after"] for row in response.data["results"]] == [8, 5]


def test_movements_carry_the_order_number_and_filter_by_reason(staff_client):
    variant = ProductVariantFactory.create(stock_quantity=0)
    order = OrderFactory.create(status=OrderStatus.PENDING)
    OrderItemFactory.create(order=order, variant=variant, quantity=2)
    set_variant_stock(variant=variant, quantity=1, actor=None)
    staff_client.post(reverse("v1:admin-order-transition", args=[order.pk]), {"to": "cancelled"})

    response = staff_client.get(reverse("v1:admin-stock-movement-list"), {"reason": "cancellation"})

    [row] = response.data["results"]
    assert row["order_id"] == order.pk
    assert row["order_number"] == order.order_number
    assert row["quantity_change"] == 2
    assert row["actor_email"] is not None
