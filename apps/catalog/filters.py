from collections.abc import Sequence
from typing import Any

import django_filters
from django.db.models import QuerySet
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.catalog.models import Product


class ProductFilter(django_filters.FilterSet):  # type: ignore[misc]  # django-filter ships no stubs
    category = django_filters.CharFilter(field_name="category__slug")
    size = django_filters.CharFilter(method="filter_by_variant")
    color = django_filters.CharFilter(method="filter_by_variant")
    min_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter()

    class Meta:
        model = Product
        fields = ("category", "size", "color", "min_price", "max_price", "in_stock")

    def filter_by_variant(
        self, queryset: QuerySet[Product], name: str, value: str
    ) -> QuerySet[Product]:
        # One product holds the same size in several colours, so joining variants
        # returns it once per match. `in_stock` reads an annotation instead of a
        # join and needs no such treatment.
        return queryset.filter(**{f"variants__{name}__slug": value}).distinct()


class DeterministicOrderingFilter(OrderingFilter):
    """Appends `pk` to client-supplied ordering so paginated pages cannot overlap."""

    def get_ordering(
        self, request: Request, queryset: QuerySet[Any], view: APIView
    ) -> Sequence[str] | None:
        ordering = super().get_ordering(request, queryset, view)
        # None means the client asked for no ordering, and the selector's own
        # deterministic order_by stands. `pk` cannot already be present: it is not
        # in ordering_fields, so DRF strips it before this runs.
        if ordering is None:
            return None
        return (*ordering, "pk")
