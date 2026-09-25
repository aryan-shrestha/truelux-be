# Merchant admin

Status: Implemented

Last updated: 2026-09-23

---

## Goal

Give the merchant a working back-office. In Phase 1 the Django admin is not a
developer convenience — it is the only tool the business has for adding products,
adjusting stock, fulfilling orders, and recovering failed payments and emails.

---

## Scope

What is included in this implementation?

- `SizeAdmin` and `ColorAdmin`, `CategoryAdmin`, `ProductAdmin` with variant and
  image inlines, `OrderAdmin`, `PaymentAdmin`
- Bulk variant generation from a chosen set of sizes and colours
- Order status transitions as admin actions calling services, with `status`
  read-only in the form
- A "Verify with Khalti" action for stranded payments
- Resend actions for the confirmation and shipping emails
- A pending-order view the merchant can work from daily

What is explicitly outside the scope?

- A custom dashboard, sales charts, or reporting
- Bulk CSV import or export
- Any change to the default Django admin theme
- Granular staff roles. Phase 1 has `is_staff` and nothing finer

---

## Context

[ADR 0002](../decisions/0002-admin-writes-go-through-the-service-layer.md) is the
governing decision and must be read before writing any `admin.py`. It splits admin
writes in two: anything with a business consequence goes through a named action
that calls a service, and `status` fields are `readonly_fields` so a naive write is
not merely discouraged but impossible. Plain catalogue editing stays naive.

Three other decisions create operational duties that land here:

- [ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md) — stock is
  held from the moment an order is placed, and **nothing releases it
  automatically**. The merchant must review pending orders or stock silently
  disappears.
- [ADR 0005](../decisions/0005-khalti-lookup-is-the-only-verification.md) — a
  customer who pays and closes the tab leaves a paid order the system thinks is
  unpaid. The only recovery is a merchant running the verify action.
- [ADR 0006](../decisions/0006-transactional-email-sends-in-request-on-commit.md) —
  a failed email is never retried. The only recovery is a merchant resending it.

All three failure modes are invisible unless the admin surfaces them.

[ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md) adds a fourth
duty, and it blocks the catalogue entirely: `size` and `color` are lookup tables
that ship **empty**, and a variant cannot be created until both hold rows. Until
`SizeAdmin` and `ColorAdmin` exist the only ways in are the Django shell and a
data migration, so they are the first thing to build here, not the last. They are
plain catalogue editing, so ADR 0002 permits a naive `ModelAdmin` with no service
layer.

---

## Planned

The intended implementation:

- `apps/catalog/admin.py`: `SizeAdmin` and `ColorAdmin` (list display with
  `sort_order` editable, slug prepopulated); `CategoryAdmin`; `ProductAdmin` with
  `ProductVariant` and `ProductImage` inlines, `prepopulated_fields` for slug,
  and a list display showing publication state and total stock
- A "Generate variants" action on `ProductAdmin` taking selected sizes and colours
  and creating the missing combinations, skipping those that already exist
- `apps/orders/admin.py`: `OrderAdmin` with `status` in `readonly_fields`, actions
  for each transition, an inline read-only view of `OrderItem`, filters on status
  and date, and search by order number and email
- A default filter or changelist link surfacing orders stuck in `pending`
- `apps/payments/admin.py`: `PaymentAdmin` with the Khalti verify action, and a
  "mark cash as collected" action calling
  `apps.payments.services.complete_cod_payment`, which `payments.md` (#8) added
  for it. Without that action a merchant cannot record collected cash at all —
  the service is currently reachable only from the Django shell
- Resend-email actions on `OrderAdmin`
- Every action reports per-object outcomes through `self.message_user`

---

## Implemented

- `apps/catalog/admin.py` — `SizeAdmin` and `ColorAdmin` (the two that unblock the
  catalogue at all), `CategoryAdmin`, `ProductAdmin` with variant and image inlines
  and an annotated total-stock column, `ProductVariantAdmin`, `ProductImageAdmin`
- The **"Generate variants"** action, with an intermediate page for choosing sizes
  and colours, creating only the missing combinations
- The **"Adjust stock"** action, and `set_variant_stock` in
  `apps/catalog/services.py` — the only way stock can be written from the admin
- `apps/orders/admin.py` — `OrderAdmin` with `status` in `readonly_fields`, a
  read-only `OrderItem` inline, status and date filters, a date hierarchy, search
  by order number, email, phone and name, and one action per transition
- `apps/payments/admin.py` — `PaymentAdmin`, entirely read-only, with
  **"Verify with Khalti"** and **"Mark cash as collected"**
- Per-object outcome reporting on every action
- `apps/catalog/tests/test_admin.py`, `apps/orders/tests/test_admin.py`,
  `apps/payments/tests/test_admin.py` — 30 tests

---

## Remaining

- ~~Resend actions for the confirmation and shipping emails.~~ Landed with
  `transactional-email.md` (#9): "Resend the confirmation email" and "Resend the
  shipping notice" on `OrderAdmin`. Neither accepts a different address — the
  message carries the order's `access_token`, so an action that could redirect it
  would be a way to take someone else's order rather than a support tool.
- **Stock cannot be set when a variant is created**, only afterwards through the
  action. `stock_quantity` is readonly on the add form as well as the change form,
  because the add form is the same unlocked write. A new variant starts at zero and
  takes one more click.
- No granular staff roles. Phase 1 has `is_staff` and nothing finer, so any staff
  user can cancel orders and read every customer's address and phone number.

---

## Decisions

### Decision: variant generation is an action, not a formset

**Decision**

The merchant selects a product, chooses sizes and colours, and runs an action that
creates the missing combinations.

**Reason**

A garment in five sizes and three colours is fifteen inline rows. Typing fifteen
rows per product, with a unique SKU on each, guarantees both errors and abandonment.

**Consequence**

SKUs are generated, not typed, so the generation scheme becomes a convention the
merchant depends on. It must be stable and readable, and changing it later does not
retroactively change existing SKUs.

### Decision: generated SKUs are built from the product slug

**Decision**

`PRODUCT-SLUG-SIZE-COLOUR`, uppercased — `BOXY-LOGO-TEE-M-BLACK`. The slug portion
is truncated to keep the whole within `sku`'s 64 characters.

**Reason**

The product slug is unique and `(product, size, color)` is unique, so the
combination is unique **whenever the slug fits** — no collision handling, no opaque
suffix, and a SKU a merchant can read off a packing list and search by.

The alternative considered was the product name's initials, which is what
`demo-seed` writes. It is shorter, but "Boxy Logo Tee" and "Black Linen Trouser"
both give `BLT`, and `sku` is globally unique, so the second product's generation
would fail on a clash the merchant could not interpret.

**Consequence**

**Uniqueness is not guaranteed when the slug is truncated.** Two products agreeing
in their first forty-odd characters produce the same SKU, and the action reports
that per product and tells the merchant to shorten a slug, rather than failing the
whole selection. The clash is caught inside its own `transaction.atomic()`: Django
wraps the changelist action in a transaction, so an `IntegrityError` caught without
a savepoint leaves the connection unusable and the result page itself fails to
render.

Changing the scheme later does not retroactively change existing SKUs, so the
catalogue would carry two conventions.

### Decision: actions report per-object results rather than failing wholesale

**Decision**

An action iterating a queryset catches `DomainError` per object, continues, and
reports successes and failures separately through `self.message_user`.

**Reason**

An unhandled exception halfway through a ten-order action leaves the merchant with
a 500 page and no idea which orders were processed. They will run it again.

**Consequence**

Actions are longer than a one-line loop. That is the cost of being usable under
partial failure.

---

## Gotchas

- **`OrderAdmin.status` must be in `readonly_fields`.** This is what makes ADR 0002
  enforceable rather than aspirational. Removing it silently reintroduces naive
  status writes that skip the shipping email.
- Admin actions operate on a queryset, so a service written for one object is
  called in a loop. Correct and cheap at Phase 1 volume; not cheap forever.
- Django's stock `UserAdmin` assumes a `username` field and raises on this user
  model. See `staff-identity.md`.
- Inline formsets write related rows directly, bypassing services. This is
  deliberately allowed for images and variants, whose only rules are database
  constraints — but it means stock must **not** be editable through the variant
  inline, or a merchant can set stock without a lock while a checkout is running.
- Saving a second primary image raises `IntegrityError`, surfacing as a 409 through
  the API and as a red admin error page here. Setting a new primary must clear the
  old one in the same transaction.
- The admin is the only authenticated surface in Phase 1. Its session cookie is the
  only credential in the system that grants write access to anything.
- **`Order.access_token` appears in no list, search or fieldset.** It is a bearer
  credential, and the admin is the one place it would otherwise be casually visible
  over someone's shoulder. `test_access_token_is_not_exposed_in_the_admin` asserts
  it is absent from both the changelist and the change page.
- **`set_variant_stock`'s row lock is not what makes it safe.** The write is
  absolute, so there is no read-modify-write to lose, and a concurrent decrement is
  serialised by its own lock and by PostgreSQL's row lock on the `UPDATE`. The lock
  buys an accurate `previous` in the audit line, and safety if the semantics ever
  change to a delta. Stated because the obvious reading of that line is wrong.
- **`PaymentAdmin` has `has_add_permission` returning False.** A payment typed by
  hand would have no gateway record behind it and no order it was taken against.
- The Khalti verify action skips cash payments **and says so**. An action that
  appears to do nothing gets run again.

---

## API

None. The Django admin is server-rendered and does not pass through DRF.

---

## Data changes

None. This feature adds no models; it operates on those defined in
`product-catalog.md`, `orders.md`, and `payments.md`.

---

## Permissions

`is_staff` is required to reach `/admin/`, and Django's model permissions and
groups apply within it. Per `convention.md`, those permissions are used by the
admin only and never by the API.

Phase 1 has no role distinction: any staff user can do anything, including
cancelling orders and viewing every customer's address and phone number. If the
brand grows past a single trusted operator, that is the first thing to revisit.

---

## Tests

30 tests. Each drives the real admin page through `client.post(reverse("admin:..."))`
as a logged-in staff user, because half of what is being asserted is that the wiring
exists at all.

`apps/catalog/tests/test_admin.py`:

- `test_generate_variants_creates_missing_combinations`
- `test_generate_variants_skips_existing_combinations`
- `test_generated_skus_do_not_collide_across_products` — two products whose initials
  agree, which is what the chosen scheme exists to survive
- `test_a_generated_sku_fits_the_column`
- `test_a_truncated_slug_collision_is_reported_not_raised`
- `test_stock_is_not_editable_through_the_variant_inline`
- `test_adjust_stock_sets_the_counted_total`
- `test_a_restock_and_a_sale_do_not_interleave`
- `test_the_action_asks_before_it_acts` — parametrised over both intermediate
  pages. Every other test posts `apply=1` and skips them, so without this a broken
  template is a 500 nobody finds until a merchant clicks the action
- `test_every_catalogue_changelist_renders` — parametrised over all six. A
  changelist fails at render time, on a bad `list_display` name or a filter on a
  field that does not exist, and nothing else in the suite would notice

`apps/orders/tests/test_admin.py`:

- `test_status_is_not_an_editable_form_field`
- `test_mark_shipped_action_moves_a_paid_order`
- `test_mark_paid_and_delivered_actions_move_an_order_along`
- `test_cancel_action_restores_variant_stock`
- `test_action_reports_partial_failure_without_raising`
- `test_access_token_is_not_exposed_in_the_admin`
- `test_order_items_cannot_be_edited`

`apps/payments/tests/test_admin.py`:

- `test_verify_action_marks_completed_payment_paid`
- `test_verify_action_reports_a_failed_payment_without_raising`
- `test_verify_action_skips_cash_payments_and_says_so`
- `test_mark_cash_collected_marks_the_order_paid`
- `test_collecting_an_already_collected_payment_is_reported_not_raised`
- `test_payments_cannot_be_added_by_hand`
- `test_payment_fields_are_read_only`

The resend actions are tested in `apps/orders/tests/test_emails.py`, with the
feature that owns the emails they send.

The service call itself is covered by
`test_mark_shipped_action_moves_a_paid_order`, and the send it triggers by
`test_shipped_email_is_sent_by_the_service_not_the_admin` in
`apps/orders/tests/test_emails.py`.

---

## Files

```text
apps/catalog/admin.py
apps/catalog/services.py                          set_variant_stock
apps/catalog/templates/admin/catalog/             the two action pages
apps/orders/admin.py
apps/payments/admin.py
apps/users/admin.py                               already existed, from #1
apps/catalog/tests/test_admin.py
apps/orders/tests/test_admin.py
apps/payments/tests/test_admin.py
```

---

## Future context

**Author this document early and implement it last.** ADR 0002 constrains every
`admin.py` in the repository, and discovering that after three apps have registered
naive `ModelAdmin` classes means rewriting all of them. That worked: nothing had to
be rewritten.

One mechanical trap for whoever adds the next `admin.py`: **`ModelAdmin` and
`TabularInline` are generic to django-stubs but not subscriptable at runtime.**
Writing `admin.ModelAdmin[Product]` raises `TypeError` at import, which surfaces as
mypy failing to construct its Django plugin rather than as anything resembling the
actual mistake. Write the base plain and add
`# type: ignore[type-arg]  # not subscriptable at runtime`, as every module here and
`apps/users/admin.py` before them do.

The merchant has three standing operational duties that no automation covers in
Phase 1: review pending orders so held stock is released, verify stranded payments,
and resend failed emails. These are not optional hygiene — each corresponds to a
documented failure mode with no automatic recovery. All three are written for
the merchant, in the merchant's language, in
[../handover.md](../handover.md#the-three-things-you-must-check-regularly).

All three duties disappear at once if an external cron and an authenticated sweep
endpoint are added. ADR 0004, ADR 0005, and ADR 0006 all anticipate needing that
same mechanism; when it is built, build it once.
