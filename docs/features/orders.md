# Orders

Status: Implemented

Last updated: 2026-09-21

---

## Goal

Own the record of what a customer bought, what they paid, where it is going, and
where it is in the fulfilment process — and let them look it up again without an
account.

---

## Scope

What is included in this implementation?

- `Order` and `OrderItem` models, with the shipping address denormalised onto the
  order
- A human-readable order number and an opaque access token
- The status lifecycle and the service functions that move an order through it
- `GET /api/v1/orders/{access_token}/` and the throttled order-number fallback
- Line items that snapshot price and product description at purchase time

What is explicitly outside the scope?

- Order creation, which belongs to `checkout.md` — this document owns the tables,
  that one owns the write path
- Payment records, which belong to `payments.md`
- Email content and triggers, which belong to `transactional-email.md`
- Returns, refunds, exchanges, or partial cancellation
- Customer accounts and order history
- Editing an order's line items after placement

---

## Context

[ADR 0003](../decisions/0003-guest-checkout-with-opaque-order-access-tokens.md)
determines the shape of this table. There is **no `user` foreign key** — not a
nullable one. Identity is the customer's email and phone captured at checkout, and
authorization is an unguessable `access_token` delivered by email.

[ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md) requires
that `status` distinguish "placed, awaiting payment" from "paid", because the first
holds stock and is a cancellation candidate and the second is not.

[ADR 0002](../decisions/0002-admin-writes-go-through-the-service-layer.md) requires
that every status transition have both a service function and an admin action, and
that `status` be read-only in the admin form.

`apps/catalog` owns `ProductVariant`. This app reads it and, during checkout,
decrements its stock — always through `apps.catalog.services`, never through
`ProductVariant.objects`.

---

## Planned

The intended implementation, delivered as described. Retained for the record of
intent:

- `Order`: UUID pk, timestamps, `order_number` (unique, human-readable),
  `access_token` (UUID, unique), `status`, `email`, `phone`, `full_name`, address
  fields, `subtotal`, `shipping_fee`, `total`, `payment_method`
- `OrderItem`: `order` FK (`CASCADE`), `variant` FK (`PROTECT`), `quantity`,
  `unit_price`, and snapshotted `product_name`, `variant_size`, `variant_color`,
  `sku`. The two snapshot columns are plain text copied from `size.name` and
  `color.name` at placement — [ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md)
  makes those lookup rows, and an order line must survive one being renamed or
  deleted
- `apps/orders/services.py`: `mark_order_paid`, `mark_order_shipped`,
  `mark_order_delivered`, `cancel_order` — each guarding the transition it performs
- `apps/orders/selectors.py`: `get_order_by_access_token`,
  `get_order_by_number_and_email`
- `apps/orders/exceptions.py`: `InvalidStatusTransition`, `OrderAlreadyShipped`,
  `OrderNotCancellable`
- `apps/orders/views.py`: two `AllowAny` read endpoints, the fallback separately
  throttled
- Status choices as module constants in `apps/orders/constants.py`

---

## Implemented

- `apps/orders/models.py` — `Order` and `OrderItem` with every column, constraint
  and index listed under Data changes. `access_token` is `UUIDField(default=uuid4,
  unique, editable=False)`; `order_number`, `subtotal`, `shipping_fee` and `total`
  are as specified
- `apps/orders/constants.py` — `OrderStatus` and `PaymentMethod` as
  `models.TextChoices`, plus the order-number prefix, sequence name and width.
  `PaymentMethod` is what `payments.md` (#8) reuses for `Payment.method`
- `apps/orders/migrations/0001_initial.py` — both tables and the
  `order_number_seq` sequence. One migration, no data migration
- `apps/orders/exceptions.py` — `InvalidStatusTransition`, `OrderAlreadyShipped`,
  `OrderNotCancellable`. `EmptyCart` belongs to `checkout.md` (#7)
- `apps/orders/services.py` — `generate_order_number`, `mark_order_paid`,
  `mark_order_shipped`, `mark_order_delivered`, `cancel_order`
- `apps/orders/selectors.py` — `get_order_by_access_token`,
  `get_order_by_number_and_email`, both prefetching `items` and both letting
  `DoesNotExist` propagate into the handler's 404
- `apps/orders/serializers.py` — `OrderItemSerializer`,
  `ShippingAddressSerializer`, `OrderReadSerializer`, `OrderLookupSerializer`.
  `access_token` appears in no `fields` tuple
- `apps/orders/views.py` and `urls.py` — `OrderDetailView` (`RetrieveAPIView`) and
  `OrderLookupView` (`APIView`, POST only), both `AllowAny`, registered into
  `api_v1_patterns`
- `config/settings/base.py` — the `order_lookup` throttle scope at `20/hour`;
  `config/settings/test.py` carries its own entry, because that override replaces
  the rates dict rather than merging into it
- `apps/orders/tests/` — `OrderFactory`, `OrderItemFactory` and 37 tests

---

## Remaining

- ~~Nothing creates an order.~~ `checkout.md` (#7) added `place_order`, which
  lives in this app's `services.py`. Orders are now created over HTTP.
- **No admin.** ADR 0002 requires an admin action per transition, calling the
  service. The services exist for it to call; `OrderAdmin` itself belongs to
  `merchant-admin.md` (#10), which is also where `status` becomes a
  `readonly_field`.
- **Nothing constrains an order to one row per variant.** Data changes never
  specified a `(order, variant)` unique constraint and none was added. `cancel_order`
  sums quantities per variant rather than assuming uniqueness, so the restore is
  correct either way; #7 decides whether to merge duplicate cart lines at placement
  or to add the constraint.

---

## Decisions

### Decision: the address is denormalised onto the order

**Decision**

Shipping address fields live as columns on `Order`, not in a separate `Address`
table.

**Reason**

With no customer accounts there is no address book, nothing to reuse an address
across, and no second owner of the data. A separate table would add a join to every
order read to model a one-to-one relationship that never varies.

More importantly, the address must be a **snapshot**. Where a parcel was sent is a
historical fact; a related row that someone later edits would rewrite history.

**Consequence**

Phase 2's saved addresses become a separate table that *populates* these columns at
checkout, rather than replacing them.

### Decision: line items snapshot name, size, colour, SKU, and price

**Decision**

`OrderItem` copies the product name, variant size and colour, SKU, and resolved
unit price at the moment of purchase.

**Reason**

The variant foreign key answers *which row*; it does not answer *what the customer
saw*. Renaming a product, correcting a colour, or repricing it must not alter a
completed order. A packing list and an invoice both need the historical values.

**Consequence**

Displaying an order never joins to the catalogue. The `variant` FK is retained for
traceability — and is `PROTECT`, so the catalogue cannot delete its way out of an
order's history.

### Decision: `order_number` comes from a Postgres sequence, and the year does not reset it

**Decision**

`order_number` is `TL-<year>-<6 digits>`, where the digits come from
`nextval('order_number_seq')`. The sequence is created in `0001_initial` and is
global: it does not restart in January, so `TL-2027-000143` follows
`TL-2026-000142`.

**Reason**

A counter derived from `SELECT MAX(...) + 1` or `Order.objects.count()` is a race
that hands two concurrent checkouts the same number, and the unique constraint
turns that into a failed order rather than a corrupted one — a customer-facing
failure for a field that carries no meaning.

Resetting the counter each year would need something to run on 1 January.
`architecture.md` states there is no in-process scheduler and no task queue, so the
only honest options were a global sequence or a runtime write to create a per-year
sequence on first use. The year is therefore a label, not a counter.

**Consequence**

Order numbers are sequential, which reveals roughly how many orders exist to anyone
who places two. That is why the lookup endpoint requires a matching email and takes
the lowest throttle in the system.

`nextval()` is exempt from transaction rollback, so a placement that fails after
reserving a number leaves a gap. Gaps are expected and are not a sign of deleted
orders.

### Decision: a paid order can still be cancelled

**Decision**

`cancel_order` accepts `pending` and `paid`, and restores stock in both cases.
`shipped` and `delivered` raise `OrderAlreadyShipped`; an order already cancelled
raises `OrderNotCancellable`.

**Reason**

[ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md) says
`status` must distinguish "placed, awaiting payment" from "paid" because "the first
holds stock and is a candidate for cancellation and the second is not". Read
literally, that would leave a paid order the merchant cannot fulfil with no
in-app cancellation at all: the stock stays committed to an order that will never
ship, and the order sits in `paid` forever.

The ADR's purpose is that stock returns exactly once, by a deliberate human act.
Cancelling from `paid` serves that purpose rather than defeating it.

**Consequence**

Refunding a cancelled Khalti payment is a manual step in Khalti's dashboard —
nothing here initiates it, and `payments.md` (#8) does not either. A merchant who
cancels a paid order must remember to refund it. When #8 lands, that is the
obvious place for a guard or a reminder.

This does not reverse ADR 0004, which decides *when stock is committed*; it settles
which states return it, which the ADR left to this document.

### Decision: `order_number` is human-readable and separate from the access token

**Decision**

Two identifiers. `order_number` is short and speakable, for the customer to quote
over the phone. `access_token` is a UUID and is the credential.

**Reason**

Collapsing them would force a choice between an unguessable identifier nobody can
read aloud and a readable identifier that is enumerable. Two fields cost one column.

**Consequence**

`order_number` may appear in logs and support conversations. `access_token` may
not — it is a credential and falls under `convention.md`'s never-log list.

---

## Gotchas

- **`access_token` is a bearer credential.** Never log it, never include it in an
  error `details`, never put it in an analytics event. It will nonetheless end up in
  browser history, so the order page must not load third-party scripts and must
  control referrer leakage.
- **Both lookup endpoints return an identical 404** for "no such order" and "the
  email does not match". A distinguishable response turns the fallback into an
  oracle that confirms which email placed which order.
- The fallback endpoint needs its own throttle scope. The global `anon` rate of
  `60/hour` is the right order of magnitude here and must not be raised — see
  `catalog-browsing.md`, which raises a *separate* scope precisely so this one can
  stay low.
- `OrderItem.variant` is `PROTECT`. A merchant deleting a variant that has been
  ordered gets an error, which is correct; the admin should steer them to
  unpublishing.
- Status transitions are guarded in the **service**, not the serializer or the
  admin. Cancelling a shipped order raises `OrderAlreadyShipped`, which surfaces as
  a 422.
- Money is `DecimalField`, never float. `total` is stored, not computed on read, so
  that a later shipping-fee change cannot alter a historical total.
- **`order_number` gaps are normal.** `nextval()` does not roll back, so a failed
  placement burns its number. Do not "fix" the gaps, and do not derive a count of
  orders from the highest number.
- **The lookup route is declared before the token route**, and the token route uses
  the `uuid` path converter, so `orders/lookup/` cannot be read as an access token.
- **`cancel_order` takes a row lock on the order, and the lock is load-bearing.**
  The status check guards a stock movement, which makes it a read-then-write on
  shared state -- `convention.md`'s rule. Without
  `select_for_update()`, two staff cancelling the same order at once both pass the
  check and both restore the stock, which inflates inventory and produces exactly
  the oversell ADR 0004 exists to prevent, reached from the other direction.
  Verified meaningful: with the lock removed,
  `test_concurrent_cancellation_restores_the_stock_only_once` fails with the stock
  restored twice.
- The lock order is order row first, then variant rows in ascending `pk` through
  `restore_variant_stock`. Anything that later locks a variant before its order
  reintroduces the deadlock ADR 0004 warns about.
- `cancel_order` sums quantities per variant before restoring, because nothing
  constrains an order to one row per variant. Building the mapping by assignment
  would silently restore only the last duplicate line.
- **`OrderItem.quantity` is an `IntegerField`, not a `PositiveIntegerField`**, for
  the reason `product-catalog.md` records about `stock_quantity`: the positive
  variant adds its own unnamed `CHECK (>= 0)` alongside the named `>= 1`
  constraint, leaving two checks of differing strength on one column.
- **Factories are called as `OrderFactory.create(...)` in this app's tests.**
  factory_boy's stubs type the bare `OrderFactory(...)` call as returning the
  factory rather than the model, which `mypy --strict` rejects the moment an
  instance is passed to a typed service. `.create()` is factory_boy's own explicit
  API and types correctly. The catalog tests use the bare call because they only
  ever read attributes off the result, which the `attr-defined` relaxation in
  `pyproject.toml` already covers.

---

## API

### Endpoint

```text
GET  /api/v1/orders/{access_token}/
POST /api/v1/orders/lookup/
```

### Request

```json
{ "order_number": "TL-2026-000142", "email": "customer@example.com" }
```

### Response

```json
{
  "order_number": "TL-2026-000142",
  "status": "shipped",
  "placed_at": "2026-09-20T10:14:00Z",
  "email": "customer@example.com",
  "phone": "98XXXXXXXX",
  "shipping": {
    "full_name": "...",
    "address_line": "...",
    "city": "...",
    "district": "..."
  },
  "items": [
    {
      "product_name": "Linen Shirt",
      "variant_size": "M",
      "variant_color": "Black",
      "sku": "LIN-SHT-M-BLK",
      "quantity": 1,
      "unit_price": "4500.00"
    }
  ],
  "subtotal": "4500.00",
  "shipping_fee": "150.00",
  "total": "4650.00",
  "payment_method": "khalti"
}
```

`access_token` is never included in the response body.

### Errors

```json
{ "error": { "code": "not_found", "message": "Not found.", "details": {} } }
```

422 with `order_already_shipped` or `order_not_cancellable` for invalid
transitions, raised by services and reached through the admin rather than the API.

---

## Data changes

**`order`** — UUID pk, timestamps, `order_number` (unique), `access_token` (UUID,
unique, indexed), `status`, `email`, `phone`, `full_name`, `address_line`, `city`,
`district`, `note`, `subtotal`, `shipping_fee`, `total` (all `DecimalField`),
`payment_method`.
Indexes on `access_token`, `order_number`, and `(status, -created_at)` for the
admin's pending-order view.
Constraints: `total >= 0`; `status` in the defined choices.

**`order_item`** — UUID pk, timestamps, `order` FK (`CASCADE`), `variant` FK
(`PROTECT`), `quantity`, `unit_price`, `product_name`, `variant_size`,
`variant_color`, `sku`.
Constraint: `quantity >= 1`.
Index on `order`.

Status values: `pending`, `paid`, `shipped`, `delivered`, `cancelled`. `pending`
means placed and awaiting payment, and holds stock.

One migration. No data migration.

---

## Permissions

`AllowAny` on both endpoints, declared explicitly.

Authorization is possession of the `access_token`, or knowledge of the order number
together with the email on the order. There is no permission class, because there
is no authenticated principal to check — the credential is the URL.

This is a deliberate departure from `architecture.md`'s ownership rule, which
assumes a `user` foreign key. ADR 0003 records why and what replaces it.

Staff see every order through the admin.

---

## Tests

37 tests. `apps/orders/tests/test_api.py`:

- `test_order_detail_by_access_token_returns_200`
- `test_order_detail_renders_the_address_as_one_object`
- `test_order_detail_with_wrong_token_returns_404`
- `test_order_response_never_contains_access_token`
- `test_order_detail_query_count_is_constant` — two items and then six, following
  the precedent `catalog-browsing.md` set
- `test_lookup_returns_the_order_for_a_matching_number_and_email`
- `test_lookup_matches_email_case_insensitively`
- `test_lookup_with_mismatched_email_returns_404`
- `test_lookup_for_unknown_order_returns_identical_404` — asserts the two response
  bodies are equal, not merely both 404
- `test_lookup_without_an_order_number_returns_400`
- `test_lookup_rejects_get`
- `test_exceeding_lookup_throttle_returns_429`
- `test_the_token_endpoint_is_not_on_the_lookup_throttle`

`apps/orders/tests/test_services.py`:

- `test_order_number_has_the_documented_shape`
- `test_order_numbers_are_unique_under_concurrency` — eight reservations across
  four threads. This is what distinguishes a sequence from `MAX(...) + 1`
- `test_mark_paid_from_pending_succeeds`, `test_mark_shipped_from_paid_succeeds`,
  `test_mark_delivered_from_shipped_succeeds`
- `test_an_illegal_transition_raises_and_leaves_the_status_alone` — parametrised
  over six wrong source states
- `test_cancelling_restores_stock` — parametrised over `pending` and `paid`
- `test_cancelling_sums_repeated_variants_before_restoring`
- `test_cancel_after_shipping_raises_and_restores_nothing` — parametrised over
  `shipped` and `delivered`, and asserts the stock did *not* move
- `test_cancelling_an_already_cancelled_order_does_not_restore_stock_twice`
- `test_concurrent_cancellation_restores_the_stock_only_once` — two threads racing
  to cancel one order. `transaction=True`, overriding the module marker, because
  the second thread runs on its own connection and cannot see data held in an
  uncommitted test transaction

`apps/orders/tests/test_models.py`:

- `test_zero_quantity_item_violates_constraint`
- `test_negative_total_violates_constraint`
- `test_duplicate_order_number_violates_constraint`
- `test_every_order_gets_a_distinct_access_token`
- `test_deleting_an_order_cascades_to_its_items`
- `test_deleting_an_ordered_variant_is_protected`

---

## Files

```text
apps/orders/
├── models.py
├── constants.py
├── services.py
├── selectors.py
├── serializers.py
├── exceptions.py
├── views.py
├── urls.py
├── migrations/
│   └── 0001_initial.py
└── tests/
    ├── factories.py
    ├── test_models.py
    ├── test_services.py
    └── test_api.py
config/settings/base.py          apps.orders, the order_lookup rate
.env.example                     DJANGO_THROTTLE_ORDER_LOOKUP
config/settings/test.py          its own order_lookup rate
config/urls.py                   api_v1_patterns
```

`admin.py` is absent by decision: ADR 0002 puts every transition behind an admin
action that calls a service, and `merchant-admin.md` (#10) owns those.

---

## Future context

This document owns the tables; `checkout.md` owns the write path that creates them.
Exactly one document may own a table's data changes, so `checkout.md`'s Data
changes section says "None" and points here.

The absence of a `user` foreign key is deliberate and is not an oversight to
correct. Phase 2 adds it as nullable, backfills nothing, and keeps token access
working for orders placed before accounts existed.

An order sitting in `pending` is holding stock that nothing will release
automatically. The `(status, -created_at)` index exists so the admin can surface
those cheaply; `merchant-admin.md` describes the duty this creates for the
merchant.
