# ADR 0002: Admin writes go through the service layer

Status: Accepted

Date: 2026-09-20

Supersedes: None

---

## Context

`architecture.md` states as a hard constraint that all writes go through services.
The Django admin breaks that by construction: `ModelAdmin.save_model` calls
`obj.save()` directly, inline formsets write related rows without consulting
anything, and a queryset-level admin action can update a thousand rows without
touching a single service function.

In Phase 1 this is not a theoretical purity problem. The admin *is* the merchant's
back-office — there is no custom dashboard. Every order that ships, ships because
someone changed a status in the admin. If that write bypasses the service layer,
the shipped-confirmation email never sends, and the customer never learns their
parcel is on the way.

So the question is not whether to allow admin writes. It is which admin writes are
allowed to be naive, and which must be routed.

## Decision

Admin writes are split by whether they carry business consequences.

**Status transitions and stock adjustments go through admin actions that call
services.** On `OrderAdmin`, `status` is not an editable form field; it is
`readonly_fields`. Moving an order forward is done with a named admin action —
"Mark selected orders as shipped" — whose implementation calls
`apps.orders.services.mark_order_shipped(...)` once per selected order.

**`save_model` is overridden wherever a service exists for the write.** Where a
model has business rules, `ModelAdmin.save_model` delegates rather than calling
`super()`.

**Plain catalogue editing stays naive.** Editing a product's name, description,
price, or images uses the default `ModelAdmin` machinery. These fields have no
invariant beyond what the model and its constraints already enforce.

## Reason

Routing *every* admin write through services would mean fighting the admin
constantly — inline formsets in particular have no clean service seam, and
rewriting `save_formset` for `ProductImage` would produce more code than the rule
protects.

Routing *no* admin write through services would mean the merchant's primary tool
is the one path that skips every business rule in the system.

The split falls naturally along a line that is easy to state and easy to review: if
changing a field should cause something else to happen — an email, a stock change,
a payment state change — it is not a form field. It is an action.

Making `status` read-only in the form is what makes the rule enforceable rather
than merely documented. An engineer cannot accidentally reintroduce a naive status
write, because the field is not there to write.

## Alternatives considered

### Declare the admin a trusted out-of-band channel

Treat admin writes as deliberately unconstrained, on the grounds that staff know
what they are doing.

Why it was not chosen: the consequence is not a corrupted row, it is a customer
who paid and heard nothing. "Staff know what they are doing" does not send an
email. It also silently weakens `architecture.md`'s stated invariant, which future
work would then reasonably assume still holds.

### Route everything, including inline formsets

Why it was not chosen: `save_formset` overrides for image inlines would add
indirection with no invariant behind it, which CLAUDE.md's anti-slop rules
explicitly prohibit. The cost is real and the benefit is zero for models whose only
rules are database constraints.

### Build a custom merchant dashboard instead of using the admin

Why it was not chosen: it is a Phase 1 budget of several weeks for a tool the
Django admin already provides, and it does not actually solve this problem — a
custom dashboard would need the same discipline about which writes call services.

## Consequences

### Positive

- Marking an order shipped always sends the shipped email, because there is one
  code path and it is the service.
- Status transitions are auditable: a named action is greppable in a way that a
  form save is not.
- Business rules cannot be bypassed by a staff member clicking the wrong field.

### Negative

- The merchant cannot correct a status by typing it. Fixing a mis-clicked
  transition requires an action that moves it back, and if no such action exists,
  the merchant is stuck. Every forward transition needs a deliberate answer about
  whether it is reversible.
- Admin actions operate on a queryset, so a service designed for one object is
  called in a loop. For Phase 1 volumes this is correct and cheap; it will not stay
  cheap forever.
- Two ways to write exist in the same file, and the boundary between them has to be
  understood rather than inferred.

### Constraints introduced

- `OrderAdmin.status` is in `readonly_fields`. This is not optional styling.
- Every order status transition has a corresponding service function and a
  corresponding admin action. Adding a status without both is incomplete.
- An admin action that calls a service must handle a `DomainError` raised partway
  through a queryset loop and report it through `self.message_user`, rather than
  letting a 500 hide which rows succeeded.

## Implementation

```text
apps/orders/admin.py       status read-only; actions calling services
apps/orders/services.py    mark_order_shipped, mark_order_delivered, cancel_order
apps/catalog/admin.py      naive product/image editing; stock via service
apps/payments/admin.py     verify-with-gateway action
docs/features/merchant-admin.md
```

## Future reconsideration

Revisit when a custom merchant dashboard replaces the admin, at which point every
write is an API call and this ADR becomes moot.

Revisit sooner if order volume makes per-object service calls in an admin action
too slow — the fix is a bulk service function, not a return to naive writes.
