from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.catalog.tests.factories import ProductVariantFactory
from apps.orders.constants import PaymentMethod
from apps.orders.models import Order, OrderItem
from apps.orders.services import generate_order_number


class OrderFactory(DjangoModelFactory[Order]):
    class Meta:
        model = Order

    order_number = factory.LazyFunction(generate_order_number)
    email = factory.Sequence(lambda n: f"customer{n}@example.com")
    phone = "9800000000"
    full_name = factory.Sequence(lambda n: f"Customer {n}")
    address_line = "1 Test Road"
    city = "Kathmandu"
    district = "Kathmandu"
    subtotal = Decimal("4500.00")
    shipping_fee = Decimal("150.00")
    total = Decimal("4650.00")
    payment_method = PaymentMethod.COD


class OrderItemFactory(DjangoModelFactory[OrderItem]):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    variant = factory.SubFactory(ProductVariantFactory)
    quantity = 1
    unit_price = Decimal("4500.00")
    product_name = "Linen Shirt"
    variant_size = "M"
    variant_color = "Black"
    sku = factory.Sequence(lambda n: f"SKU-ORDER-{n}")
