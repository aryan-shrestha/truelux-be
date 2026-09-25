from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.serializers import BaseSerializer

from apps.catalog.filters import DeterministicOrderingFilter, ProductFilter
from apps.catalog.models import Category, Product
from apps.catalog.selectors import (
    get_published_product_by_slug,
    list_category_tree,
    list_published_products,
)
from apps.catalog.serializers import (
    CategoryTreeSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)
from apps.core.throttling import ResilientScopedRateThrottle

CATALOG_THROTTLE_SCOPE = "catalog"


class ProductViewSet(viewsets.ReadOnlyModelViewSet[Product]):
    permission_classes = (AllowAny,)
    throttle_classes = (ResilientScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    # The storefront needs readable, SEO-stable URLs, which is the one place this
    # repository looks up a detail route by something other than a UUID.
    lookup_field = "slug"
    filter_backends = (DjangoFilterBackend, DeterministicOrderingFilter, SearchFilter)
    filterset_class = ProductFilter
    search_fields = ("name", "description")
    ordering_fields = ("name", "base_price", "created_at")

    def get_queryset(self) -> QuerySet[Product]:
        return list_published_products()

    def get_object(self) -> Product:
        # Not the default implementation: detail needs the variant prefetch that
        # the list queryset deliberately omits. A missing or unpublished slug
        # raises DoesNotExist, which the handler turns into the documented 404.
        product = get_published_product_by_slug(slug=self.kwargs[self.lookup_field])
        self.check_object_permissions(self.request, product)
        return product

    def get_serializer_class(self) -> type[BaseSerializer[Product]]:
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer


class CategoryListView(ListAPIView[Category]):
    permission_classes = (AllowAny,)
    throttle_classes = (ResilientScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    serializer_class = CategoryTreeSerializer
    # Navigation is useless truncated, and a merchant adding a 26th root category
    # would otherwise watch it disappear from the storefront menu.
    pagination_class = None

    def get_queryset(self) -> QuerySet[Category]:
        return list_category_tree()
