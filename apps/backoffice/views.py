from typing import Any, ClassVar
from uuid import UUID

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.backoffice import selectors
from apps.backoffice.filters import AdminOrderFilter, AdminProductFilter
from apps.backoffice.serializers import (
    AdminBrandSerializer,
    AdminCategorySerializer,
    AdminImageSerializer,
    AdminOrderDetailSerializer,
    AdminOrderListSerializer,
    AdminProductDetailSerializer,
    AdminProductListSerializer,
    AdminShadeSerializer,
    AdminSizeSerializer,
    AdminVariantSerializer,
    BrandWriteSerializer,
    CategoryWriteSerializer,
    DashboardSerializer,
    ImageCreateSerializer,
    ImageUpdateSerializer,
    ProductWriteSerializer,
    ShadeWriteSerializer,
    SizeWriteSerializer,
    TransitionSerializer,
    VariantWriteSerializer,
)
from apps.catalog.filters import DeterministicOrderingFilter
from apps.catalog.models import Brand, Category, Product, Shade, Size
from apps.catalog.services import (
    add_product_image,
    create_product,
    create_taxonomy_entry,
    create_variant,
    delete_product,
    delete_product_image,
    delete_taxonomy_entry,
    delete_variant,
    update_product,
    update_product_image,
    update_taxonomy_entry,
    update_variant,
)
from apps.orders.models import Order
from apps.orders.services import transition_order

ADMIN_THROTTLE_SCOPE = "admin"
JSON_AND_MULTIPART = (JSONParser, MultiPartParser, FormParser)


class StaffAPIView(APIView):
    """The one permission policy for /api/v1/admin/ (ADR 0013): JWT only (ADR 0012),
    active staff only. The Django admin's session is deliberately not accepted."""

    authentication_classes = (JWTAuthentication,)
    permission_classes = (IsAuthenticated, IsAdminUser)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = ADMIN_THROTTLE_SCOPE


def _validated(
    serializer_class: type[BaseSerializer[Any]], request: Request, **kwargs: Any
) -> dict[str, Any]:
    serializer = serializer_class(data=request.data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class DashboardView(StaffAPIView):
    @extend_schema(responses={200: DashboardSerializer})
    def get(self, request: Request) -> Response:
        return Response(DashboardSerializer(selectors.get_dashboard()).data)


class ProductListView(StaffAPIView, ListAPIView[Product]):
    serializer_class = AdminProductListSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, DeterministicOrderingFilter)
    filterset_class = AdminProductFilter
    search_fields = ("name", "variants__sku")
    ordering_fields = ("name", "base_price", "created_at")

    def get_queryset(self) -> QuerySet[Product]:
        return selectors.list_products()

    @extend_schema(request=ProductWriteSerializer, responses={201: AdminProductDetailSerializer})
    def post(self, request: Request) -> Response:
        fields = _validated(ProductWriteSerializer, request)
        is_published = fields.pop("is_published", False)

        product = create_product(fields=fields, is_published=is_published)

        return Response(
            AdminProductDetailSerializer(selectors.get_product(product_id=product.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class ProductDetailView(StaffAPIView):
    @extend_schema(responses={200: AdminProductDetailSerializer})
    def get(self, request: Request, product_id: UUID) -> Response:
        return Response(
            AdminProductDetailSerializer(selectors.get_product(product_id=product_id)).data
        )

    @extend_schema(request=ProductWriteSerializer, responses={200: AdminProductDetailSerializer})
    def patch(self, request: Request, product_id: UUID) -> Response:
        fields = _validated(ProductWriteSerializer, request, partial=True)
        is_published = fields.pop("is_published", None)

        update_product(
            product=selectors.get_product(product_id=product_id),
            fields=fields,
            is_published=is_published,
        )

        return Response(
            AdminProductDetailSerializer(selectors.get_product(product_id=product_id)).data
        )

    @extend_schema(responses={204: None})
    def delete(self, request: Request, product_id: UUID) -> Response:
        delete_product(product=selectors.get_product(product_id=product_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductVariantCreateView(StaffAPIView):
    @extend_schema(request=VariantWriteSerializer, responses={201: AdminVariantSerializer})
    def post(self, request: Request, product_id: UUID) -> Response:
        fields = _validated(VariantWriteSerializer, request)
        stock_quantity = fields.pop("stock_quantity", 0)

        variant = create_variant(
            product=selectors.get_product(product_id=product_id),
            fields=fields,
            stock_quantity=stock_quantity,
        )

        return Response(
            AdminVariantSerializer(selectors.get_variant(variant_id=variant.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class VariantDetailView(StaffAPIView):
    @extend_schema(request=VariantWriteSerializer, responses={200: AdminVariantSerializer})
    def patch(self, request: Request, variant_id: UUID) -> Response:
        fields = _validated(VariantWriteSerializer, request, partial=True)
        stock_quantity = fields.pop("stock_quantity", None)

        update_variant(
            variant=selectors.get_variant(variant_id=variant_id),
            fields=fields,
            stock_quantity=stock_quantity,
        )

        return Response(AdminVariantSerializer(selectors.get_variant(variant_id=variant_id)).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, variant_id: UUID) -> Response:
        delete_variant(variant=selectors.get_variant(variant_id=variant_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductImageCreateView(StaffAPIView):
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(request=ImageCreateSerializer, responses={201: AdminImageSerializer})
    def post(self, request: Request, product_id: UUID) -> Response:
        fields = _validated(ImageCreateSerializer, request)

        image = add_product_image(product=selectors.get_product(product_id=product_id), **fields)

        return Response(AdminImageSerializer(image).data, status=status.HTTP_201_CREATED)


class ImageDetailView(StaffAPIView):
    @extend_schema(request=ImageUpdateSerializer, responses={200: AdminImageSerializer})
    def patch(self, request: Request, image_id: UUID) -> Response:
        fields = _validated(ImageUpdateSerializer, request, partial=True)
        is_primary = fields.pop("is_primary", None)

        image = update_product_image(
            image=selectors.get_image(image_id=image_id), fields=fields, is_primary=is_primary
        )

        return Response(AdminImageSerializer(image).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, image_id: UUID) -> Response:
        delete_product_image(image=selectors.get_image(image_id=image_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaxonomyListView[E: (Brand, Category, Shade, Size)](StaffAPIView, GenericAPIView[E]):
    model: type[E]
    write_serializer_class: ClassVar[type[BaseSerializer[Any]]]
    pagination_class = None

    def get(self, request: Request) -> Response:
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def post(self, request: Request) -> Response:
        fields = _validated(self.write_serializer_class, request)

        entry = create_taxonomy_entry(model=self.model, fields=fields)

        return Response(
            self.get_serializer(self.get_queryset().get(pk=entry.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class TaxonomyDetailView[E: (Brand, Category, Shade, Size)](StaffAPIView, GenericAPIView[E]):
    model: type[E]
    write_serializer_class: ClassVar[type[BaseSerializer[Any]]]

    def patch(self, request: Request, entry_id: UUID) -> Response:
        fields = _validated(self.write_serializer_class, request, partial=True)

        update_taxonomy_entry(entry=self.model.objects.get(pk=entry_id), fields=fields)

        return Response(self.get_serializer(self.get_queryset().get(pk=entry_id)).data)

    def delete(self, request: Request, entry_id: UUID) -> Response:
        delete_taxonomy_entry(entry=self.model.objects.get(pk=entry_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(responses={200: AdminBrandSerializer(many=True)}),
    post=extend_schema(request=BrandWriteSerializer, responses={201: AdminBrandSerializer}),
)
class BrandListView(TaxonomyListView[Brand]):
    model = Brand
    serializer_class = AdminBrandSerializer
    write_serializer_class = BrandWriteSerializer
    parser_classes = JSON_AND_MULTIPART

    def get_queryset(self) -> QuerySet[Brand]:
        return selectors.list_brands()


@extend_schema_view(
    patch=extend_schema(request=BrandWriteSerializer, responses={200: AdminBrandSerializer}),
    delete=extend_schema(responses={204: None}),
)
class BrandDetailView(TaxonomyDetailView[Brand]):
    model = Brand
    serializer_class = AdminBrandSerializer
    write_serializer_class = BrandWriteSerializer
    parser_classes = JSON_AND_MULTIPART

    def get_queryset(self) -> QuerySet[Brand]:
        return selectors.list_brands()


@extend_schema_view(
    get=extend_schema(responses={200: AdminCategorySerializer(many=True)}),
    post=extend_schema(request=CategoryWriteSerializer, responses={201: AdminCategorySerializer}),
)
class CategoryListView(TaxonomyListView[Category]):
    model = Category
    serializer_class = AdminCategorySerializer
    write_serializer_class = CategoryWriteSerializer

    def get_queryset(self) -> QuerySet[Category]:
        return selectors.list_categories()


@extend_schema_view(
    patch=extend_schema(request=CategoryWriteSerializer, responses={200: AdminCategorySerializer}),
    delete=extend_schema(responses={204: None}),
)
class CategoryDetailView(TaxonomyDetailView[Category]):
    model = Category
    serializer_class = AdminCategorySerializer
    write_serializer_class = CategoryWriteSerializer

    def get_queryset(self) -> QuerySet[Category]:
        return selectors.list_categories()


@extend_schema_view(
    get=extend_schema(responses={200: AdminShadeSerializer(many=True)}),
    post=extend_schema(request=ShadeWriteSerializer, responses={201: AdminShadeSerializer}),
)
class ShadeListView(TaxonomyListView[Shade]):
    model = Shade
    serializer_class = AdminShadeSerializer
    write_serializer_class = ShadeWriteSerializer

    def get_queryset(self) -> QuerySet[Shade]:
        return selectors.list_shades()


@extend_schema_view(
    patch=extend_schema(request=ShadeWriteSerializer, responses={200: AdminShadeSerializer}),
    delete=extend_schema(responses={204: None}),
)
class ShadeDetailView(TaxonomyDetailView[Shade]):
    model = Shade
    serializer_class = AdminShadeSerializer
    write_serializer_class = ShadeWriteSerializer

    def get_queryset(self) -> QuerySet[Shade]:
        return selectors.list_shades()


@extend_schema_view(
    get=extend_schema(responses={200: AdminSizeSerializer(many=True)}),
    post=extend_schema(request=SizeWriteSerializer, responses={201: AdminSizeSerializer}),
)
class SizeListView(TaxonomyListView[Size]):
    model = Size
    serializer_class = AdminSizeSerializer
    write_serializer_class = SizeWriteSerializer

    def get_queryset(self) -> QuerySet[Size]:
        return selectors.list_sizes()


@extend_schema_view(
    patch=extend_schema(request=SizeWriteSerializer, responses={200: AdminSizeSerializer}),
    delete=extend_schema(responses={204: None}),
)
class SizeDetailView(TaxonomyDetailView[Size]):
    model = Size
    serializer_class = AdminSizeSerializer
    write_serializer_class = SizeWriteSerializer

    def get_queryset(self) -> QuerySet[Size]:
        return selectors.list_sizes()


class OrderListView(StaffAPIView, ListAPIView[Order]):
    serializer_class = AdminOrderListSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter)
    filterset_class = AdminOrderFilter
    search_fields = ("order_number", "full_name", "email", "phone")

    def get_queryset(self) -> QuerySet[Order]:
        return selectors.list_orders()


class OrderDetailView(StaffAPIView):
    @extend_schema(responses={200: AdminOrderDetailSerializer})
    def get(self, request: Request, order_id: UUID) -> Response:
        return Response(AdminOrderDetailSerializer(selectors.get_order(order_id=order_id)).data)


class OrderTransitionView(StaffAPIView):
    @extend_schema(request=TransitionSerializer, responses={200: AdminOrderDetailSerializer})
    def post(self, request: Request, order_id: UUID) -> Response:
        target = _validated(TransitionSerializer, request)["to"]

        transition_order(order=selectors.get_order(order_id=order_id), to=target)

        return Response(AdminOrderDetailSerializer(selectors.get_order(order_id=order_id)).data)
