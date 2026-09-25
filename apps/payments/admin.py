from collections.abc import Callable

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.core.exceptions import DomainError
from apps.payments.models import Payment
from apps.payments.services import complete_cod_payment, verify_khalti_payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    list_display = ("order", "method", "status", "amount", "created_at")
    list_filter = ("method", "status", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    search_fields = ("order__order_number", "order__email", "pidx", "transaction_id")
    actions = ("verify_with_khalti", "mark_cash_collected")

    # Everything is readonly. A payment is a record of what happened, and `status`
    # in particular moves only through the services below -- ADR 0002. `pidx` and
    # `transaction_id` are Khalti's identifiers, not ours to edit.
    readonly_fields = (
        "order",
        "method",
        "status",
        "amount",
        "pidx",
        "transaction_id",
        "raw_status",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Payment]:
        payments: QuerySet[Payment] = super().get_queryset(request)
        return payments.select_related("order")

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Payments are created by checkout, never by hand: one typed here would have
        # no gateway record behind it and no order it was taken against.
        return False

    def _run(
        self,
        request: HttpRequest,
        payments: QuerySet[Payment],
        operation: Callable[[Payment], Payment],
        verb: str,
    ) -> None:
        """Applies an operation per payment, reporting successes and failures apart.

        An unhandled exception halfway through leaves the merchant with a 500 and no
        idea which payments were processed. The deliberate exception to
        convention.md's "no try/except around service calls": the caller is a person
        looking at a page, not an API client reading an envelope.
        """
        succeeded: list[str] = []
        failed: list[str] = []

        for payment in payments:
            try:
                operation(payment)
            except DomainError as exc:
                failed.append(f"{payment.order.order_number} ({exc.message})")
            else:
                succeeded.append(payment.order.order_number)

        if succeeded:
            self.message_user(
                request, f"{verb} {len(succeeded)}: {', '.join(succeeded)}.", messages.SUCCESS
            )
        if failed:
            self.message_user(
                request, f"Could not {verb.lower()} {'; '.join(failed)}.", messages.WARNING
            )

    @admin.action(description="Verify selected payments with Khalti")
    def verify_with_khalti(self, request: HttpRequest, queryset: QuerySet[Payment]) -> None:
        """ADR 0005's only recovery for a customer who paid and closed the tab.

        Khalti sends no webhook, so nothing detects that payment until someone runs
        this. It is safe to run on an already-verified payment.
        """
        verifiable = queryset.exclude(pidx__isnull=True)

        skipped = queryset.count() - verifiable.count()
        if skipped:
            # Saying so, rather than appearing to do nothing: a merchant who
            # selected the whole page would otherwise get no message at all.
            self.message_user(
                request,
                f"Skipped {skipped} with no Khalti reference -- those are cash on delivery.",
                messages.INFO,
            )

        self._run(
            request,
            verifiable,
            lambda payment: verify_khalti_payment(pidx=str(payment.pidx)),
            "Verified",
        )

    @admin.action(description="Mark cash as collected on selected payments")
    def mark_cash_collected(self, request: HttpRequest, queryset: QuerySet[Payment]) -> None:
        """Marks a cash-on-delivery payment collected, and its order paid."""
        self._run(
            request, queryset, lambda payment: complete_cod_payment(payment=payment), "Collected"
        )
