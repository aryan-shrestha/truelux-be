from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import ResilientScopedRateThrottle
from apps.orders.constants import PaymentMethod
from apps.orders.models import Order
from apps.orders.selectors import get_order_by_access_token, get_order_by_number_and_email
from apps.orders.serializers import (
    CheckoutResponseSerializer,
    CheckoutSerializer,
    OrderLookupSerializer,
    OrderReadSerializer,
)
from apps.orders.services import place_order
from apps.payments.services import initiate_khalti_payment, record_cod_payment

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
    throttle_classes = (ResilientScopedRateThrottle,)
    throttle_scope = ORDER_LOOKUP_THROTTLE_SCOPE

    @extend_schema(request=OrderLookupSerializer, responses={200: OrderReadSerializer})
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = OrderLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = get_order_by_number_and_email(**serializer.validated_data)

        return Response(OrderReadSerializer(order).data)


class CheckoutView(APIView):
    # No authentication exists in Phase 1, so anyone may place an order. The
    # security boundary here is input distrust, not identity: the only things taken
    # from the body are variant ids, quantities, and contact and address fields.
    permission_classes = (AllowAny,)
    throttle_classes = (ResilientScopedRateThrottle,)
    throttle_scope = CHECKOUT_THROTTLE_SCOPE

    @extend_schema(
        request=CheckoutSerializer,
        responses={
            201: OpenApiResponse(
                response=CheckoutResponseSerializer,
                description=(
                    "For a Khalti order the body also carries `payment_url`, the page to "
                    "send the customer to. Cash on delivery omits the key."
                ),
            )
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = place_order(**serializer.validated_data)

        # ADR 0005 puts the payment handoff here, after place_order's transaction
        # has committed, never inside it: the Khalti call is an external HTTP
        # request of unbounded duration, and holding the variant row locks across it
        # blocks every other buyer of the same variants.
        data = CheckoutResponseSerializer(order).data
        if order.payment_method == PaymentMethod.KHALTI:
            data["payment_url"] = initiate_khalti_payment(order=order)
        else:
            record_cod_payment(order=order)

        return Response(data, status=status.HTTP_201_CREATED)
