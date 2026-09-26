from datetime import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.backoffice.constants import SHOP_TIME_ZONE
from apps.catalog.tests.factories import ProductVariantFactory
from apps.core.exceptions import DomainError
from apps.orders.constants import ALLOWED_TRANSITIONS, OrderStatus
from apps.orders.models import Order
from apps.orders.services import transition_order
from apps.orders.tests.factories import OrderFactory, OrderItemFactory

pytestmark = pytest.mark.django_db


def _transition(staff_client, order, to):
    return staff_client.post(reverse("v1:admin-order-transition", args=[order.pk]), {"to": to})


def test_order_list_item_shape(staff_client):
    order = OrderFactory(full_name="Sita Sharma", total=Decimal("5400.00"))
    OrderItemFactory(order=order, quantity=2)
    OrderItemFactory(order=order, quantity=1)

    item = staff_client.get(reverse("v1:admin-order-list")).data["results"][0]

    assert item["order_number"] == order.order_number
    assert item["full_name"] == "Sita Sharma"
    assert item["total"] == "5400.00"
    assert item["item_count"] == 3
    assert "access_token" not in item


def test_order_list_filters(staff_client):
    pending = OrderFactory(status=OrderStatus.PENDING, phone="9811111111")
    shipped = OrderFactory(status=OrderStatus.SHIPPED, email="asha@example.com")
    OrderFactory(status=OrderStatus.DELIVERED)
    url = reverse("v1:admin-order-list")

    by_status = staff_client.get(url, {"status": ["pending", "shipped"]})
    by_phone = staff_client.get(url, {"search": "9811111111"})
    by_email = staff_client.get(url, {"search": "asha@"})
    by_date = staff_client.get(url, {"created_after": "2000-01-01", "created_before": "2000-01-02"})

    assert {o["id"] for o in by_status.data["results"]} == {str(pending.pk), str(shipped.pk)}
    assert [o["id"] for o in by_phone.data["results"]] == [str(pending.pk)]
    assert [o["id"] for o in by_email.data["results"]] == [str(shipped.pk)]
    assert by_date.data["count"] == 0


@pytest.mark.parametrize("order_count", [2, 8])
def test_order_list_query_count_is_constant(staff_client, django_assert_num_queries, order_count):
    for _ in range(order_count):
        OrderItemFactory()

    with django_assert_num_queries(2):
        staff_client.get(reverse("v1:admin-order-list"))


def test_order_detail(staff_client):
    order = OrderFactory(status=OrderStatus.CONFIRMED)
    OrderItemFactory(order=order, quantity=2, unit_price=Decimal("1650.00"), variant_shade="")

    response = staff_client.get(reverse("v1:admin-order-detail", args=[order.pk]))

    assert response.data["allowed_transitions"] == ["shipped", "cancelled"]
    assert response.data["payment_method"] == "cod"
    assert response.data["items"][0]["line_total"] == "3300.00"
    assert response.data["items"][0]["variant_shade"] == ""
    assert "access_token" not in response.data


@pytest.mark.parametrize(
    ("start", "to", "end"),
    [
        (OrderStatus.PENDING, "confirmed", OrderStatus.CONFIRMED),
        (OrderStatus.CONFIRMED, "shipped", OrderStatus.SHIPPED),
        (OrderStatus.SHIPPED, "delivered", OrderStatus.DELIVERED),
        (OrderStatus.PENDING, "cancelled", OrderStatus.CANCELLED),
        (OrderStatus.CONFIRMED, "cancelled", OrderStatus.CANCELLED),
    ],
)
def test_each_allowed_transition(staff_client, start, to, end):
    order = OrderFactory(status=start)

    response = _transition(staff_client, order, to)

    assert response.status_code == 200
    assert response.data["status"] == end
    order.refresh_from_db()
    assert order.status == end


@pytest.mark.parametrize(
    ("start", "to", "code"),
    [
        (OrderStatus.PENDING, "shipped", "invalid_status_transition"),
        (OrderStatus.CONFIRMED, "confirmed", "invalid_status_transition"),
        (OrderStatus.DELIVERED, "shipped", "invalid_status_transition"),
        (OrderStatus.SHIPPED, "cancelled", "order_already_shipped"),
        (OrderStatus.CANCELLED, "cancelled", "order_not_cancellable"),
    ],
)
def test_invalid_transitions_return_the_service_codes(staff_client, start, to, code):
    order = OrderFactory(status=start)

    response = _transition(staff_client, order, to)

    assert response.status_code == 422
    assert response.data["error"]["code"] == code


def test_an_unknown_target_status_is_a_400(staff_client):
    response = _transition(staff_client, OrderFactory(), "paid")

    assert response.status_code == 400


def test_cancelling_restores_stock(staff_client):
    variant = ProductVariantFactory(stock_quantity=3)
    order = OrderFactory(status=OrderStatus.CONFIRMED)
    OrderItemFactory(order=order, variant=variant, quantity=2)

    _transition(staff_client, order, "cancelled")

    variant.refresh_from_db()
    assert variant.stock_quantity == 5


@pytest.mark.parametrize("start", list(ALLOWED_TRANSITIONS))
@pytest.mark.parametrize(
    "to", [OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.CANCELLED]
)
def test_allowed_transitions_agree_with_the_services(start, to):
    order = OrderFactory.create(status=start)

    try:
        transition_order(order=order, to=to)
    except DomainError:
        moved = False
    else:
        moved = True

    assert moved == (to in ALLOWED_TRANSITIONS[start])


def test_order_list_date_filters_use_the_shop_day_inclusively(staff_client):
    def placed_at(day, hour, minute):
        order = OrderFactory()
        at = datetime(2026, 9, day, hour, minute, tzinfo=SHOP_TIME_ZONE)
        Order.objects.filter(pk=order.pk).update(created_at=at)
        return str(order.pk)

    # 00:30 on the 25th in Kathmandu is 18:45 on the 24th in UTC.
    first_minute = placed_at(25, 0, 30)
    last_minute = placed_at(25, 23, 59)
    placed_at(24, 23, 59)
    placed_at(26, 0, 0)
    url = reverse("v1:admin-order-list")

    on_the_day = staff_client.get(
        url, {"created_after": "2026-09-25", "created_before": "2026-09-25"}
    )
    after = staff_client.get(url, {"created_after": "2026-09-25"})
    before = staff_client.get(url, {"created_before": "2026-09-24"})

    assert {o["id"] for o in on_the_day.data["results"]} == {first_minute, last_minute}
    assert after.data["count"] == 3
    assert before.data["count"] == 1


def test_order_list_created_before_the_last_representable_day_lists_everything(staff_client):
    OrderFactory()

    response = staff_client.get(reverse("v1:admin-order-list"), {"created_before": "9999-12-31"})

    assert response.data["count"] == 1
