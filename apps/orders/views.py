from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.orders.selectors import get_order_by_access_token, get_order_by_number_and_email
from apps.orders.serializers import (
    CheckoutResponseSerializer,
    CheckoutSerializer,
    OrderLookupSerializer,
    OrderReadSerializer,
)
from apps.orders.services import place_order
from apps.payments.services import record_cod_payment

ORDER_LOOKUP_THROTTLE_SCOPE = "order_lookup"
CHECKOUT_THROTTLE_SCOPE = "checkout"


class OrderDetailView(RetrieveAPIView[Order]):
    # The access token in the URL is the credential (ADR 0003). There is no
    # authenticated principal, so there is no permission class to own this.
    permission_classes = (AllowAny,)
    serializer_class = OrderReadSerializer

    def get_object(self) -> Order:
        return get_order_by_access_token(access_token=self.kwargs["access_token"])


class OrderLookupView(APIView):
    permission_classes = (AllowAny,)
    # Its own scope, kept low: order numbers run in sequence, so this is the one
    # endpoint where guessing is cheap. catalog-browsing.md took a separate scope
    # precisely so the global anon rate could stay low for this.
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = ORDER_LOOKUP_THROTTLE_SCOPE

    @extend_schema(request=OrderLookupSerializer, responses={200: OrderReadSerializer})
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = OrderLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = get_order_by_number_and_email(**serializer.validated_data)

        return Response(OrderReadSerializer(order).data)


class CheckoutView(APIView):
    # Guest checkout (ADR 0003): the boundary is input distrust, not identity. Only
    # variant ids, quantities, contact and address fields are read from the body.
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = CHECKOUT_THROTTLE_SCOPE

    @extend_schema(request=CheckoutSerializer, responses={201: CheckoutResponseSerializer})
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = place_order(**serializer.validated_data)
        record_cod_payment(order=order)

        return Response(CheckoutResponseSerializer(order).data, status=status.HTTP_201_CREATED)
