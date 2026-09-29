from typing import Any

from rest_framework import serializers

from apps.orders.constants import PaymentMethod
from apps.orders.models import Order, OrderItem, ShippingSettings
from apps.orders.services import CartPrice, PricedLine


class OrderItemSerializer(serializers.ModelSerializer[OrderItem]):
    class Meta:
        model = OrderItem
        # The snapshot columns, not the variant: a line must read the same after the
        # catalogue renames the product or retires the shade.
        fields = (
            "product_name",
            "variant_size",
            "variant_shade",
            "sku",
            "quantity",
            "unit_price",
        )


class ShippingAddressSerializer(serializers.Serializer[Order]):
    full_name = serializers.CharField(read_only=True)
    address_line = serializers.CharField(read_only=True)
    city = serializers.CharField(read_only=True)
    district = serializers.CharField(read_only=True)


class OrderReadSerializer(serializers.ModelSerializer[Order]):
    placed_at = serializers.DateTimeField(source="created_at", read_only=True)
    shipping = ShippingAddressSerializer(source="*", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        # `access_token` is absent deliberately. It is the credential that reaches
        # this endpoint; echoing it back into a page, a log or an analytics event
        # is how a bearer token in a URL escapes.
        fields = (
            "order_number",
            "status",
            "placed_at",
            "email",
            "phone",
            "shipping",
            "items",
            "subtotal",
            "shipping_fee",
            "total",
            "payment_method",
        )


class OrderLookupSerializer(serializers.Serializer[Order]):
    order_number = serializers.CharField()
    email = serializers.EmailField()


class CheckoutItemSerializer(serializers.Serializer[dict[str, object]]):
    variant_id = serializers.UUIDField()
    # Load-bearing, not decorative: decrement_variant_stock raises a plain
    # ValueError on a non-positive quantity by design, so without this bound a
    # client sending 0 receives a 500 instead of a 400.
    quantity = serializers.IntegerField(min_value=1)


class CheckoutSerializer(serializers.Serializer[dict[str, object]]):
    """Validates shape only.

    Checking stock here would be a check-then-act race. Availability is decided
    inside the row lock, in the service, never before it. There is deliberately no
    price field: a price in the request body is a price the customer can edit.
    """

    items = CheckoutItemSerializer(many=True, allow_empty=False)

    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32)

    full_name = serializers.CharField(max_length=200)
    address_line = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=100)
    district = serializers.CharField(max_length=100)
    note = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")

    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)


class CheckoutResponseSerializer(serializers.ModelSerializer[Order]):
    class Meta:
        model = Order
        # Smaller than OrderReadSerializer by design: the customer has just sent
        # the address, and `access_token` reaches them only by email.
        fields = ("order_number", "status", "subtotal", "shipping_fee", "total")


class QuoteSerializer(serializers.Serializer[dict[str, object]]):
    items = CheckoutItemSerializer(many=True, allow_empty=False)
    # Optional: the bag page quotes before the customer has said where it is going.
    district = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True, default=None
    )

    def validate_district(self, value: str | None) -> str | None:
        return value or None


def _money(**kwargs: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, **kwargs)


class QuoteLineSerializer(serializers.Serializer[PricedLine]):
    variant_id = serializers.UUIDField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    unit_price = _money()
    line_total = _money()


class QuoteResponseSerializer(serializers.Serializer[CartPrice]):
    subtotal = _money()
    shipping_fee = _money(allow_null=True)
    discount = _money()
    total = _money(allow_null=True)
    free_shipping_remaining = _money(allow_null=True)
    lines = QuoteLineSerializer(many=True, read_only=True)


class ShippingSettingsSerializer(serializers.ModelSerializer[ShippingSettings]):
    class Meta:
        model = ShippingSettings
        fields = ("inside_valley_fee", "outside_valley_fee", "free_shipping_threshold")
