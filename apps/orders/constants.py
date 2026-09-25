from django.db import models

ORDER_NUMBER_PREFIX = "TL"
# A Postgres sequence, created in 0001_initial. nextval() is atomic and, unlike a
# SELECT MAX(...) + 1, cannot hand the same number to two concurrent checkouts.
ORDER_NUMBER_SEQUENCE = "order_number_seq"
ORDER_NUMBER_DIGITS = 6


class OrderStatus(models.TextChoices):
    # `pending` means placed and awaiting payment. Per ADR 0004 it holds stock, and
    # nothing releases that stock until a human cancels the order.
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class PaymentMethod(models.TextChoices):
    COD = "cod", "Cash on delivery"
