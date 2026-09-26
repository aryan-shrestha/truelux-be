from datetime import date, timedelta

import django_filters
from django.db.models import Exists, OuterRef, QuerySet

from apps.backoffice.constants import LOW_STOCK_THRESHOLD
from apps.backoffice.selectors import start_of_shop_day
from apps.catalog.models import Product, ProductVariant
from apps.orders.constants import OrderStatus
from apps.orders.models import Order


class AdminProductFilter(django_filters.FilterSet):  # type: ignore[misc]  # django-filter ships no stubs
    brand = django_filters.UUIDFilter(field_name="brand_id")
    category = django_filters.UUIDFilter(field_name="category_id")
    is_published = django_filters.BooleanFilter()
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")

    class Meta:
        model = Product
        fields = ("brand", "category", "is_published", "low_stock")

    def filter_low_stock(
        self, queryset: QuerySet[Product], name: str, value: bool
    ) -> QuerySet[Product]:
        low = Exists(
            ProductVariant.objects.filter(
                product=OuterRef("pk"), stock_quantity__lte=LOW_STOCK_THRESHOLD
            )
        )
        return queryset.filter(low) if value else queryset.exclude(low)


class AdminOrderFilter(django_filters.FilterSet):  # type: ignore[misc]  # django-filter ships no stubs
    status = django_filters.MultipleChoiceFilter(choices=OrderStatus.choices)
    created_after = django_filters.DateFilter(method="filter_created_after")
    created_before = django_filters.DateFilter(method="filter_created_before")

    class Meta:
        model = Order
        fields = ("status", "created_after", "created_before")

    # Days are the shop's (Asia/Kathmandu), matching the dashboard KPIs that link here.
    def filter_created_after(
        self, queryset: QuerySet[Order], name: str, value: date
    ) -> QuerySet[Order]:
        return queryset.filter(created_at__gte=start_of_shop_day(value))

    def filter_created_before(
        self, queryset: QuerySet[Order], name: str, value: date
    ) -> QuerySet[Order]:
        if value == date.max:
            return queryset
        return queryset.filter(created_at__lt=start_of_shop_day(value + timedelta(days=1)))
