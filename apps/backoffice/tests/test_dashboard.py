from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from freezegun import freeze_time

from apps.backoffice.constants import SHOP_TIME_ZONE
from apps.catalog.tests.factories import ProductVariantFactory
from apps.orders.constants import OrderStatus
from apps.orders.models import Order
from apps.orders.tests.factories import OrderFactory

pytestmark = pytest.mark.django_db

# 10:00 in Kathmandu on 25 September is 04:15 UTC.
NOW = datetime(2026, 9, 25, 10, 0, tzinfo=SHOP_TIME_ZONE)


def _order_placed(at, *, total, status=OrderStatus.PENDING):
    order = OrderFactory(total=Decimal(total), status=status)
    Order.objects.filter(pk=order.pk).update(created_at=at)
    return order


@freeze_time(NOW)
def test_revenue_excludes_cancelled_orders_and_uses_the_shop_day(staff_client):
    _order_placed(NOW - timedelta(hours=1), total="5400.00")
    _order_placed(NOW - timedelta(hours=2), total="999.00", status=OrderStatus.CANCELLED)
    # 23:30 on the 24th in Kathmandu: yesterday for the shop, so not "today".
    _order_placed(NOW.replace(hour=0) - timedelta(minutes=30), total="1000.00")
    _order_placed(NOW - timedelta(days=10), total="2000.00", status=OrderStatus.DELIVERED)
    _order_placed(NOW - timedelta(days=40), total="7000.00")

    revenue = staff_client.get(reverse("v1:admin-dashboard")).data["revenue"]

    assert revenue == {"today": "5400.00", "last_7_days": "6400.00", "last_30_days": "8400.00"}


@freeze_time(NOW)
def test_sales_by_day_has_30_zero_filled_days_oldest_first(staff_client):
    _order_placed(NOW - timedelta(hours=1), total="3000.00")
    _order_placed(NOW - timedelta(hours=2), total="600.00")

    days = staff_client.get(reverse("v1:admin-dashboard")).data["sales_by_day"]

    assert len(days) == 30
    assert days[0] == {"date": "2026-08-27", "orders": 0, "revenue": "0.00"}
    assert days[-1] == {"date": "2026-09-25", "orders": 2, "revenue": "3600.00"}


def test_orders_by_status_lists_every_status(staff_client):
    OrderFactory.create_batch(2, status=OrderStatus.PENDING)
    OrderFactory(status=OrderStatus.CANCELLED)

    counts = staff_client.get(reverse("v1:admin-dashboard")).data["orders_by_status"]

    assert counts == {"pending": 2, "confirmed": 0, "shipped": 0, "delivered": 0, "cancelled": 1}


def test_recent_orders_are_the_five_newest(staff_client):
    orders = [_order_placed(NOW - timedelta(hours=hours), total="1.00") for hours in range(7)]

    recent = staff_client.get(reverse("v1:admin-dashboard")).data["recent_orders"]

    assert [order["id"] for order in recent] == [str(order.pk) for order in orders[:5]]


def test_low_stock_is_ordered_lowest_first_and_capped_at_ten(staff_client):
    for quantity in [5, 0, 3, 6, 1, 2, 4, 0, 1, 2, 3, 5]:
        ProductVariantFactory(stock_quantity=quantity)

    low_stock = staff_client.get(reverse("v1:admin-dashboard")).data["low_stock"]

    assert len(low_stock) == 10
    assert [row["stock_quantity"] for row in low_stock] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 5]
    assert {"variant_id", "product_id", "product_name", "sku", "size", "shade"} <= set(low_stock[0])
    assert low_stock[0]["shade"] is None
