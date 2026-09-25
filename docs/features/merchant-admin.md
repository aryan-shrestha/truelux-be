# Merchant admin (Django admin)

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Keep the Django admin, now at `/django-admin/`, as a complete superuser back-office
alongside the TrueLux admin app (`admin-api.md`), writing through the same services.

---

## Scope

What is included in this implementation?

- `BrandAdmin`, `CategoryAdmin`, `SizeAdmin`, `ShadeAdmin`, `ProductAdmin` (variant
  and image inlines), `ProductVariantAdmin`, `ProductImageAdmin`, `OrderAdmin`,
  `PaymentAdmin`, `UserAdmin`
- Actions for everything with a consequence: publishing, variant generation, stock
  counts, primary images, order transitions, email resends, cash collection
- Staff account management (the admin API deliberately has none)

What is explicitly outside the scope?

- Theming, dashboards and reports (the admin app's dashboard covers reporting)
- Granular roles: `is_staff` and `is_superuser` only

---

## Context

[ADR 0002](../decisions/0002-admin-writes-go-through-the-service-layer.md): a field
whose change has a consequence is read-only and changed by an action calling a
service. It is moved from `/admin/` to `/django-admin/` so `/admin` is never
confused with the admin app.

---

## Implemented

- `apps/catalog/admin.py`
  - `BrandAdmin`, `SizeAdmin`, `ShadeAdmin`, `CategoryAdmin` share `LookupAdmin`
    (editable `sort_order`, prepopulated slug, search).
  - `ProductAdmin`: `is_published` read-only; actions **Publish** / **Unpublish**
    (`set_product_published`, refused per product without variants) and
    **Generate variants** (chosen sizes × chosen shades, or shadeless when no shade
    is ticked; SKUs from the product, size and shade slugs).
  - `ProductVariantAdmin`: `stock_quantity` read-only; **Adjust stock** calls
    `set_variant_stock`.
  - `ProductImageAdmin`: `is_primary` read-only; **Make primary** calls
    `update_product_image`.
- `apps/orders/admin.py` — `OrderAdmin`, `status` read-only, `access_token` never
  shown; actions **confirmed**, **shipped**, **delivered**, **cancel**, and the two
  resends. Line items are read-only snapshots.
- `apps/payments/admin.py` — `PaymentAdmin`, read-only, **Mark cash as collected**.
- `apps/users/admin.py` — `UserAdmin` for staff accounts.
- `config/urls.py` — mounted at `/django-admin/`.

---

## Remaining

None.

---

## Decisions

### Decision: actions report per-object results

**Decision**

Transition, publish and cash actions catch `DomainError` per row and report
successes and failures separately.

**Reason**

The caller is a person; a 500 halfway through a batch leaves them not knowing what
happened.

### Decision: generated SKUs come from slugs

**Decision**

`generate_sku` builds `PRODUCT-SLUG-SIZE[-SHADE]`, truncated to 64 characters; a
truncation clash is reported, not suffixed.

---

## Gotchas

- Variant and image inlines on the product page save through formsets (ADR 0002
  exempts inlines). Ticking a second primary there is rejected by the form's
  constraint validation; use **Make primary**.
- New images added in the admin are never primary until promoted.
- Action code runs inside the changelist transaction, so variant generation uses a
  savepoint to survive an `IntegrityError`.

---

## Permissions

Django admin login (session) for `is_staff` users; model permissions apply. The API
does not accept this session.

---

## Tests

- `apps/catalog/tests/test_admin.py` — variant generation (with and without shades),
  SKU scheme and clashes, stock read-only and the locked adjust action, publish and
  unpublish, make-primary, every changelist renders.
- `apps/orders/tests/test_admin.py`, `apps/payments/tests/test_admin.py`,
  `apps/users/tests/test_admin.py` (including the `/django-admin/` mount).

---

## Files

```text
apps/catalog/admin.py
apps/catalog/templates/admin/catalog/
apps/orders/admin.py
apps/payments/admin.py
apps/users/admin.py
```
