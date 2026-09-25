from django.conf import settings

from apps.core.email import send_email
from apps.orders.models import Order

CONFIRMATION_TEMPLATE = "orders/email/order_confirmation"
SHIPPED_TEMPLATE = "orders/email/order_shipped"


def _order_context(order: Order) -> dict[str, object]:
    return {
        "order": order,
        "items": order.items.all(),
        # The customer's only route back to their order (ADR 0003). It appears here
        # and in the templates only inside the link -- never as a bare string, and
        # never in a log line.
        "order_url": f"{str(settings.STOREFRONT_URL).rstrip('/')}/orders/{order.access_token}",
    }


def send_order_confirmation(*, order: Order) -> bool:
    return send_email(
        to=order.email,
        subject=f"Order {order.order_number} received",
        template_name=CONFIRMATION_TEMPLATE,
        context=_order_context(order),
        reference=order.order_number,
    )


def send_order_shipped(*, order: Order) -> bool:
    return send_email(
        to=order.email,
        subject=f"Order {order.order_number} is on its way",
        template_name=SHIPPED_TEMPLATE,
        context=_order_context(order),
        reference=order.order_number,
    )
