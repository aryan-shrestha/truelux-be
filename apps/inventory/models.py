from django.conf import settings
from django.db import models

from apps.catalog.models import ProductVariant
from apps.core.models import TimeStampedModel, UUIDModel
from apps.orders.models import Order


class MovementReason(models.TextChoices):
    STOCKTAKE = "stocktake", "Stocktake"
    SALE = "sale", "Sale"
    CANCELLATION = "cancellation", "Order cancelled"
    RECEIVED = "received", "Received"
    RETURNED = "returned", "Returned"
    DAMAGED = "damaged", "Damaged"
    EXPIRED = "expired", "Expired"
    TESTER = "tester", "Tester or sample"
    CORRECTION = "correction", "Correction"


INCREASING_REASONS = (MovementReason.CANCELLATION, MovementReason.RECEIVED, MovementReason.RETURNED)
DECREASING_REASONS = (
    MovementReason.SALE,
    MovementReason.DAMAGED,
    MovementReason.EXPIRED,
    MovementReason.TESTER,
)
# What staff may record as a delta. Sales and cancellations come only from orders,
# and a stocktake is an absolute count through set_variant_stock.
MANUAL_REASONS = (
    MovementReason.RECEIVED,
    MovementReason.RETURNED,
    MovementReason.DAMAGED,
    MovementReason.EXPIRED,
    MovementReason.TESTER,
    MovementReason.CORRECTION,
)


class StockMovement(UUIDModel, TimeStampedModel):
    """One change to ProductVariant.stock_quantity, written in the same locked
    transaction as the change itself (ADR 0019). Rows are never updated."""

    # SET_NULL rather than PROTECT: deleting a never-ordered variant must keep
    # working, and `sku` keeps the history readable once the row is gone.
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, related_name="stock_movements"
    )
    sku = models.CharField(max_length=64)
    reason = models.CharField(max_length=16, choices=MovementReason.choices)
    quantity_change = models.IntegerField()
    balance_after = models.IntegerField()
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements"
    )
    # Null for the storefront and for management commands.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    note = models.TextField(blank=True)

    class Meta:
        db_table = "stock_movement"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reason__in=MovementReason.values),
                name="stock_movement_reason_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(balance_after__gte=0),
                name="stock_movement_balance_not_negative",
            ),
            # A stocktake may confirm the count unchanged; every other movement moves
            # stock, in the direction its reason implies.
            models.CheckConstraint(
                condition=models.Q(reason=MovementReason.STOCKTAKE)
                | models.Q(reason__in=INCREASING_REASONS, quantity_change__gt=0)
                | models.Q(reason__in=DECREASING_REASONS, quantity_change__lt=0)
                | (models.Q(reason=MovementReason.CORRECTION) & ~models.Q(quantity_change=0)),
                name="stock_movement_direction_matches_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity_change:+d} {self.sku} ({self.reason})"
