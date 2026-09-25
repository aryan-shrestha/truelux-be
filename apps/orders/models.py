import uuid

from django.db import models

from apps.catalog.models import ProductVariant
from apps.core.models import TimeStampedModel, UUIDModel
from apps.orders.constants import OrderStatus, PaymentMethod


class Order(UUIDModel, TimeStampedModel):
    order_number = models.CharField(max_length=32, unique=True)
    # The credential, per ADR 0003. Possession of it is the whole authorization
    # story, so it is never logged and never serialised.
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )

    email = models.EmailField()
    phone = models.CharField(max_length=32)

    full_name = models.CharField(max_length=200)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    note = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2)
    # Stored rather than computed on read, so a later change to the shipping fee
    # cannot rewrite what a customer was charged.
    total = models.DecimalField(max_digits=10, decimal_places=2)

    payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices)

    class Meta:
        db_table = "order"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="order_status_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total__gte=0), name="order_total_not_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=OrderStatus.values), name="order_status_valid"
            ),
        ]

    def __str__(self) -> str:
        return self.order_number


class OrderItem(UUIDModel, TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # PROTECT: deleting a variant that has been ordered would destroy the record of
    # what the customer bought. The merchant unpublishes instead.
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.PROTECT, related_name="order_items"
    )

    # IntegerField, not PositiveIntegerField: the latter emits its own unnamed
    # CHECK (>= 0), which would sit alongside the named constraint below as a
    # second, weaker check on the same column. ProductVariant.stock_quantity
    # carries the same note for the same reason.
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Snapshots. The foreign key answers which row; these answer what the customer
    # saw. Renaming a product or a colour must not alter a completed order, and
    # ADR 0007 made size and colour rows that can be renamed or deleted.
    product_name = models.CharField(max_length=200)
    variant_size = models.CharField(max_length=50)
    variant_color = models.CharField(max_length=50)
    sku = models.CharField(max_length=64)

    class Meta:
        db_table = "order_item"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="order_item_quantity_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.sku}"
