from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.exceptions import DomainError
from apps.core.throttling import ResilientScopedRateThrottle
from apps.payments.services import verify_khalti_payment

PAYMENT_RETURN_THROTTLE_SCOPE = "payment_return"


class KhaltiReturnView(APIView):
    # The customer arrives from Khalti's domain with no session and, under ADR
    # 0003, no account. What protects this endpoint is not authentication but what
    # it accepts: one opaque `pidx`, and a server-to-server lookup the caller
    # cannot forge.
    permission_classes = (AllowAny,)
    throttle_classes = (ResilientScopedRateThrottle,)
    throttle_scope = PAYMENT_RETURN_THROTTLE_SCOPE

    @extend_schema(
        parameters=[OpenApiParameter("pidx", OpenApiTypes.STR, OpenApiParameter.QUERY)],
        responses={
            302: OpenApiResponse(
                description=(
                    "Redirects the browser to the storefront: the order page once the "
                    "payment is verified, otherwise `/orders/failed?reason=<code>`."
                )
            )
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponseRedirect:
        # `status`, `amount` and `transaction_id` also arrive here and are all
        # editable by whoever holds the URL. ADR 0005: the redirect is a trigger,
        # never evidence. Only `pidx` is read, and even it is only a lookup key.
        pidx = request.query_params.get("pidx", "")

        try:
            payment = verify_khalti_payment(pidx=pidx)
        except DomainError as exc:
            # The one endpoint in the system answering a browser rather than an API
            # client, so a JSON 422 would be a dead end for the customer. An unknown
            # pidx is deliberately not caught: DoesNotExist reaches the handler as
            # the documented 404, because a pidx this system never issued means a
            # hand-crafted URL, not a customer coming back from Khalti.
            return HttpResponseRedirect(
                f"{self._storefront}/orders/failed?{urlencode({'reason': exc.code})}"
            )

        return HttpResponseRedirect(f"{self._storefront}/orders/{payment.order.access_token}")

    @property
    def _storefront(self) -> str:
        return str(settings.STOREFRONT_URL).rstrip("/")
