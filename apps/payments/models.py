from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel
from apps.orders.constants import PaymentMethod
from apps.orders.models import Order


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Payment(UUIDModel, TimeStampedModel):
    # PROTECT: a payment record must outlive any attempt to tidy up orders.
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Khalti's payment identifier, and the only thing read from the return redirect.
    # Null for cash on delivery: PostgreSQL treats NULLs as distinct, so a unique
    # column holds as many of them as there are COD orders. Do not give it a default
    # to "fix" the nulls -- that would make every COD row collide.
    pidx = models.CharField(max_length=128, unique=True, null=True, blank=True)
    # Blank rather than null, unlike `pidx`: for these two, "" and NULL would mean
    # the same thing, and a string column with both spellings of absent is the
    # ambiguity DJ001 exists to prevent. `pidx` keeps its NULL because the unique
    # constraint depends on NULLs being distinct.
    transaction_id = models.CharField(max_length=128, blank=True, default="")
    raw_status = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "payment"
        ordering = ["-created_at"]
        indexes = [
            # `pidx` is not declared here: unique=True already builds its index, and
            # a second declaration would mean two identical indexes on one column.
            models.Index(fields=["status", "-created_at"], name="payment_status_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="payment_amount_not_negative"
            ),
            # Negated rather than listing COD, so a third method added later is not
            # silently exempted from needing its own identifier.
            models.CheckConstraint(
                condition=~models.Q(method=PaymentMethod.KHALTI) | models.Q(pidx__isnull=False),
                name="payment_khalti_requires_pidx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.amount} for {self.order.order_number}"
