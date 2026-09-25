from collections.abc import Sequence
from typing import Any

import django_filters
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema_field
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.catalog.models import Brand, Product


@extend_schema_field({"type": "array", "items": {"type": "string"}})
class SlugMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):  # type: ignore[misc]  # django-filter ships no stubs
    pass


class ProductFilter(django_filters.FilterSet):  # type: ignore[misc]  # django-filter ships no stubs
    brand = SlugMultipleChoiceFilter(
        field_name="brand__slug",
        to_field_name="slug",
        queryset=Brand.objects.all(),
    )
    category = django_filters.CharFilter(field_name="category__slug")
    size = django_filters.CharFilter(method="filter_by_variant")
    shade = django_filters.CharFilter(method="filter_by_variant")
    min_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter()

    class Meta:
        model = Product
        fields = ("brand", "category", "size", "shade", "min_price", "max_price", "in_stock")

    def filter_by_variant(
        self, queryset: QuerySet[Product], name: str, value: str
    ) -> QuerySet[Product]:
        # A product holds one size in several shades, so the join repeats it.
        return queryset.filter(**{f"variants__{name}__slug": value}).distinct()


class DeterministicOrderingFilter(OrderingFilter):
    """Appends `pk` to client-supplied ordering so paginated pages cannot overlap."""

    def get_ordering(
        self, request: Request, queryset: QuerySet[Any], view: APIView
    ) -> Sequence[str] | None:
        ordering = super().get_ordering(request, queryset, view)
        # None: no client ordering, so the selector's deterministic order_by stands.
        if ordering is None:
            return None
        return (*ordering, "pk")
