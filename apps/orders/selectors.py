from uuid import UUID

from apps.orders.constants import SHIPPING_SETTINGS_ID
from apps.orders.models import Order, ShippingSettings


def get_order_by_access_token(*, access_token: UUID) -> Order:
    return Order.objects.prefetch_related("items").get(access_token=access_token)


def get_order_by_number_and_email(*, order_number: str, email: str) -> Order:
    # Both lookups raise DoesNotExist, which the handler turns into the same 404.
    # ADR 0003 requires "no such order" and "that email did not place it" to be
    # indistinguishable, or the fallback confirms which address bought what.
    return Order.objects.prefetch_related("items").get(
        order_number=order_number, email__iexact=email
    )


def get_shipping_settings() -> ShippingSettings:
    return ShippingSettings.objects.get(pk=SHIPPING_SETTINGS_ID)
