from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.inventory.models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display = (
        "created_at",
        "sku",
        "reason",
        "quantity_change",
        "balance_after",
        "order",
        "actor",
    )
    list_filter = ("reason", "created_at")
    date_hierarchy = "created_at"
    search_fields = ("sku", "order__order_number")

    def get_queryset(self, request: HttpRequest) -> QuerySet[StockMovement]:
        movements: QuerySet[StockMovement] = super().get_queryset(request)
        return movements.select_related("order", "actor")

    # The ledger is history. A stock change is made through a service, which writes
    # its own row (ADR 0019).
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
