from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel
from apps.orders.constants import PaymentMethod
from apps.orders.models import Order


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"


class Payment(UUIDModel, TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "payment"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="payment_status_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="payment_amount_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.amount} for {self.order.order_number}"
