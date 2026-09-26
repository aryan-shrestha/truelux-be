from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.serializers import BaseSerializer
from rest_framework.throttling import ScopedRateThrottle

from apps.catalog.filters import DeterministicOrderingFilter, ProductFilter
from apps.catalog.models import Brand, Category, Product, Shade, Size, SkinType
from apps.catalog.selectors import (
    get_active_brand_by_slug,
    get_published_product_by_slug,
    list_active_brands,
    list_category_tree,
    list_published_products,
    list_shades_in_use,
    list_sizes_in_use,
    list_skin_types_in_use,
)
from apps.catalog.serializers import (
    BrandSerializer,
    CategoryTreeSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ShadeSerializer,
    SizeSerializer,
    SkinTypeSerializer,
)

CATALOG_THROTTLE_SCOPE = "catalog"


class ProductViewSet(viewsets.ReadOnlyModelViewSet[Product]):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    # Readable, SEO-stable storefront URLs: the one detail route not looked up by UUID.
    lookup_field = "slug"
    filter_backends = (DjangoFilterBackend, DeterministicOrderingFilter, SearchFilter)
    filterset_class = ProductFilter
    search_fields = ("name", "description")
    ordering_fields = ("name", "base_price", "created_at")

    def get_queryset(self) -> QuerySet[Product]:
        return list_published_products()

    def get_object(self) -> Product:
        # Detail needs the variant prefetch the list queryset deliberately omits.
        product = get_published_product_by_slug(slug=self.kwargs[self.lookup_field])
        self.check_object_permissions(self.request, product)
        return product

    def get_serializer_class(self) -> type[BaseSerializer[Product]]:
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer


class BrandViewSet(viewsets.ReadOnlyModelViewSet[Brand]):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    serializer_class = BrandSerializer
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self) -> QuerySet[Brand]:
        return list_active_brands()

    def get_object(self) -> Brand:
        brand = get_active_brand_by_slug(slug=self.kwargs[self.lookup_field])
        self.check_object_permissions(self.request, brand)
        return brand


# The taxonomy lists are unpaginated: storefront navigation and filters are useless
# truncated.
class CategoryListView(ListAPIView[Category]):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    serializer_class = CategoryTreeSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Category]:
        return list_category_tree()


class ShadeListView(ListAPIView[Shade]):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    serializer_class = ShadeSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Shade]:
        return list_shades_in_use()


class SizeListView(ListAPIView[Size]):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    serializer_class = SizeSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Size]:
        return list_sizes_in_use()


class SkinTypeListView(ListAPIView[SkinType]):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = CATALOG_THROTTLE_SCOPE
    serializer_class = SkinTypeSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[SkinType]:
        return list_skin_types_in_use()
