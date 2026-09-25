from collections.abc import Callable

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.core.exceptions import DomainError
from apps.orders.emails import send_order_confirmation, send_order_shipped
from apps.orders.models import Order, OrderItem
from apps.orders.services import (
    cancel_order,
    confirm_order,
    mark_order_delivered,
    mark_order_shipped,
)


class OrderItemInline(admin.TabularInline):  # type: ignore[type-arg]  # not subscriptable at runtime
    model = OrderItem
    extra = 0
    can_delete = False
    # Every field is a snapshot taken at placement. Editing one would rewrite what
    # the customer bought, which is the whole reason these columns exist.
    readonly_fields = (
        "variant",
        "product_name",
        "variant_size",
        "variant_shade",
        "sku",
        "quantity",
        "unit_price",
    )
    fields = readonly_fields

    def has_add_permission(self, request: HttpRequest, obj: Order | None = None) -> bool:
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):  # type: ignore[type-arg]  # not subscriptable at runtime
    inlines = (OrderItemInline,)
    list_display = ("order_number", "status", "full_name", "total", "payment_method", "created_at")
    list_filter = ("status", "payment_method", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    search_fields = ("order_number", "email", "phone", "full_name")
    actions = (
        "confirm",
        "mark_shipped",
        "mark_delivered",
        "cancel",
        "resend_confirmation",
        "resend_shipping_notice",
    )

    # `status` is read-only so it moves only through the transition services, which
    # guard it and send the shipping email (ADR 0002). `access_token` is a bearer
    # credential, so it appears in no list, search or fieldset.
    readonly_fields = (
        "order_number",
        "status",
        "subtotal",
        "shipping_fee",
        "total",
        "payment_method",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("order_number", "status", "payment_method")}),
        ("Customer", {"fields": ("email", "phone")}),
        ("Shipping", {"fields": ("full_name", "address_line", "city", "district", "note")}),
        ("Money", {"fields": ("subtotal", "shipping_fee", "total")}),
        ("Dates", {"fields": ("created_at", "updated_at")}),
    )

    def _run(
        self,
        request: HttpRequest,
        orders: QuerySet[Order],
        transition: Callable[..., Order],
        verb: str,
    ) -> None:
        """Applies a transition per order, reporting successes and failures apart.

        An unhandled exception halfway through a ten-order action leaves the
        merchant with a 500 and no idea which orders were processed, so they run it
        again. This is the deliberate exception to convention.md's "no try/except
        around service calls": the caller is a person looking at a page.
        """
        succeeded: list[str] = []
        failed: list[str] = []

        for order in orders:
            try:
                transition(order=order)
            except DomainError as exc:
                failed.append(f"{order.order_number} ({exc.message})")
            else:
                succeeded.append(order.order_number)

        if succeeded:
            self.message_user(
                request, f"{verb} {len(succeeded)}: {', '.join(succeeded)}.", messages.SUCCESS
            )
        if failed:
            self.message_user(
                request, f"Could not {verb.lower()} {'; '.join(failed)}.", messages.WARNING
            )

    @admin.action(description="Mark selected orders as confirmed")
    def confirm(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._run(request, queryset, confirm_order, "Confirmed")

    @admin.action(description="Mark selected orders as shipped")
    def mark_shipped(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._run(request, queryset, mark_order_shipped, "Marked shipped")

    @admin.action(description="Mark selected orders as delivered")
    def mark_delivered(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._run(request, queryset, mark_order_delivered, "Marked delivered")

    @admin.action(description="Cancel selected orders and return their stock")
    def cancel(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._run(request, queryset, cancel_order, "Cancelled")

    def _resend(
        self,
        request: HttpRequest,
        orders: QuerySet[Order],
        send: Callable[..., bool],
        what: str,
    ) -> None:
        """Re-sends to the address on the order, and to no other.

        ADR 0006 retries nothing, so this is the only recovery a failed email has.
        The message carries the order's access_token, which is why the recipient is
        never a parameter: an action that could redirect it would be a way to take
        someone else's order, not a support tool.
        """
        sent: list[str] = []
        failed: list[str] = []

        for order in orders.prefetch_related("items"):
            target = sent if send(order=order) else failed
            target.append(order.order_number)

        if sent:
            self.message_user(
                request, f"Re-sent the {what} for {', '.join(sent)}.", messages.SUCCESS
            )
        if failed:
            self.message_user(
                request,
                f"Could not send the {what} for {', '.join(failed)}. See the error log.",
                messages.ERROR,
            )

    @admin.action(description="Resend the confirmation email")
    def resend_confirmation(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._resend(request, queryset, send_order_confirmation, "confirmation")

    @admin.action(description="Resend the shipping notice")
    def resend_shipping_notice(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._resend(request, queryset, send_order_shipped, "shipping notice")
