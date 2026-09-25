from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import Count, DecimalField, Prefetch, QuerySet, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.backoffice.constants import (
    LOW_STOCK_LIMIT,
    LOW_STOCK_THRESHOLD,
    RECENT_ORDER_LIMIT,
    SALES_WINDOW_DAYS,
    SHOP_TIME_ZONE,
)
from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Shade,
    Size,
)
from apps.orders.constants import OrderStatus
from apps.orders.models import Order

_ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))


def list_products() -> QuerySet[Product]:
    return (
        Product.objects.select_related("brand", "category")
        .annotate(
            variant_count=Count("variants"),
            total_stock=Coalesce(Sum("variants__stock_quantity"), 0),
        )
        .prefetch_related("images")
        .order_by("sort_order", "-created_at", "pk")
    )


def get_product(*, product_id: UUID) -> Product:
    variants = Prefetch(
        "variants",
        queryset=ProductVariant.objects.select_related("size", "shade").order_by(
            "size__sort_order", "shade__sort_order", "sku"
        ),
    )
    return (
        Product.objects.select_related("brand", "category")
        .prefetch_related(variants, "images")
        .get(pk=product_id)
    )


def get_variant(*, variant_id: UUID) -> ProductVariant:
    return ProductVariant.objects.select_related("product", "size", "shade").get(pk=variant_id)


def get_image(*, image_id: UUID) -> ProductImage:
    return ProductImage.objects.get(pk=image_id)


def list_brands() -> QuerySet[Brand]:
    return Brand.objects.annotate(product_count=Count("products")).order_by("sort_order", "name")


def list_categories() -> QuerySet[Category]:
    return Category.objects.annotate(product_count=Count("products")).order_by("sort_order", "name")


def list_shades() -> QuerySet[Shade]:
    return Shade.objects.annotate(variant_count=Count("variants")).order_by("sort_order", "name")


def list_sizes() -> QuerySet[Size]:
    return Size.objects.annotate(variant_count=Count("variants")).order_by("sort_order", "name")


def list_orders() -> QuerySet[Order]:
    return Order.objects.annotate(item_count=Coalesce(Sum("items__quantity"), 0)).order_by(
        "-created_at", "pk"
    )


def get_order(*, order_id: UUID) -> Order:
    return Order.objects.prefetch_related("items").get(pk=order_id)


def _start_of_shop_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=SHOP_TIME_ZONE)


def _revenue_since(orders: QuerySet[Order], since: datetime) -> Decimal:
    total: Decimal = orders.filter(created_at__gte=since).aggregate(
        total=Coalesce(Sum("total"), _ZERO)
    )["total"]
    return total


def get_dashboard() -> dict[str, Any]:
    today = timezone.now().astimezone(SHOP_TIME_ZONE).date()
    window_start = today - timedelta(days=SALES_WINDOW_DAYS - 1)
    earning = Order.objects.exclude(status=OrderStatus.CANCELLED)

    counts = dict(Order.objects.values_list("status").annotate(count=Count("pk")))

    daily = {
        row["day"]: row
        for row in earning.filter(created_at__gte=_start_of_shop_day(window_start))
        .annotate(day=TruncDate("created_at", tzinfo=SHOP_TIME_ZONE))
        .values("day")
        .annotate(orders=Count("pk"), revenue=Sum("total"))
    }
    sales_by_day = []
    for offset in range(SALES_WINDOW_DAYS):
        day = window_start + timedelta(days=offset)
        row = daily.get(day)
        sales_by_day.append(
            {
                "date": day,
                "orders": row["orders"] if row else 0,
                "revenue": row["revenue"] if row else Decimal("0.00"),
            }
        )

    return {
        "orders_by_status": {status: counts.get(status, 0) for status in OrderStatus.values},
        "revenue": {
            "today": _revenue_since(earning, _start_of_shop_day(today)),
            "last_7_days": _revenue_since(earning, _start_of_shop_day(today - timedelta(days=6))),
            "last_30_days": _revenue_since(earning, _start_of_shop_day(window_start)),
        },
        "sales_by_day": sales_by_day,
        "recent_orders": list(list_orders()[:RECENT_ORDER_LIMIT]),
        "low_stock": list(
            ProductVariant.objects.filter(stock_quantity__lte=LOW_STOCK_THRESHOLD)
            .select_related("product", "size", "shade")
            .order_by("stock_quantity", "sku")[:LOW_STOCK_LIMIT]
        ),
    }
