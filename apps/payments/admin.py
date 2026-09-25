from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.core.exceptions import DomainError
from apps.payments.models import Payment
from apps.payments.services import complete_cod_payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display = ("order", "method", "status", "amount", "created_at")
    list_filter = ("method", "status", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    search_fields = ("order__order_number", "order__email")
    actions = ("mark_cash_collected",)
    # A payment is a record of what happened; status moves only through the service (ADR 0002).
    readonly_fields = ("order", "method", "status", "amount", "created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Payment]:
        payments: QuerySet[Payment] = super().get_queryset(request)
        return payments.select_related("order")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.action(description="Mark cash as collected on selected payments")
    def mark_cash_collected(self, request: HttpRequest, queryset: QuerySet[Payment]) -> None:
        # Per-row reporting rather than letting one DomainError 500 the whole batch:
        # the caller is a person looking at a page, not an API client.
        collected: list[str] = []
        failed: list[str] = []

        for payment in queryset:
            try:
                complete_cod_payment(payment=payment)
            except DomainError as exc:
                failed.append(f"{payment.order.order_number} ({exc.message})")
            else:
                collected.append(payment.order.order_number)

        if collected:
            self.message_user(
                request, f"Collected {len(collected)}: {', '.join(collected)}.", messages.SUCCESS
            )
        if failed:
            self.message_user(request, f"Could not collect {'; '.join(failed)}.", messages.WARNING)
