# Checkout

Status: Implemented

Last updated: 2026-09-23

---

## Goal

Turn a cart held in the customer's browser into a durable order, without trusting
anything the browser says about prices or availability, and without two simultaneous
buyers claiming the same last item.

---

## Scope

What is included in this implementation?

- `POST /api/v1/checkout/` — validate a submitted cart and place an order
- Server-side re-resolution of every price and every stock level
- Shipping fee calculation
- The transaction boundary, the lock protocol, and the lock ordering
- Price and description snapshotting onto order lines
- Handing off to the payment method chosen by the customer

What is explicitly outside the scope?

- The `Order` and `OrderItem` models, which belong to `orders.md`
- Payment initiation and verification, which belong to `payments.md`
- Any server-side cart storage. The cart lives in the browser
- Discount codes, gift cards, and tax calculation
- Address validation against a postal database

---

## Context

There is no cart table. The storefront keeps the cart in `localStorage` and submits
it as a list of variant ids and quantities. Everything in that payload is attacker
controlled, including any price the client believes applies.

[ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md) is the
governing decision. Stock is decremented **here**, at placement, before the customer
is sent to the payment gateway. Locks are taken with `select_for_update()` on every
variant in the cart, **in ascending `pk` order**, because a cart containing two
variants locked in opposite orders by two concurrent checkouts deadlocks and
Postgres resolves it by killing one transaction.

[ADR 0005](../decisions/0005-khalti-lookup-is-the-only-verification.md) requires
that the Khalti initiate call happen **outside** this transaction. It is an external
HTTP call of unbounded duration, and holding both a Supabase pooler slot and the
variant row locks across it is how a small instance stops serving other buyers.

[ADR 0003](../decisions/0003-guest-checkout-with-opaque-order-access-tokens.md)
means there is no authenticated user. Contact details come from the request body.

---

## Planned

The intended implementation:

- `CheckoutSerializer` validating shape only: a non-empty `items` list of
  `variant_id` and `quantity`, contact fields, address fields, and
  `payment_method` — no queries, per `convention.md`. **`quantity` must be an
  `IntegerField(min_value=1)`**: `decrement_variant_stock` raises a plain
  `ValueError` on a non-positive quantity, deliberately, because that means a
  broken caller rather than a rejected customer. Without the serializer bound, a
  client sending `"quantity": 0` gets a 500 instead of a 400
- `apps/orders/services.py::place_order`, taking plain arguments, owning the
  transaction:
  1. Call `apps.catalog.services.decrement_variant_stock(quantities=...)` with
     the whole cart. It takes the lock on every variant in one ascending-`pk`
     `select_for_update()`, rejects unknown and unpublished variants with
     `VariantUnavailable`, rejects shortfalls with `InsufficientStock`,
     decrements, and **returns the locked variants keyed by id**
  2. Read each unit price off the returned variant's `.price` property, which
     resolves `price_override` against the product's base price. Do not refetch:
     the rows are already locked and already carry their product
  3. Compute subtotal, shipping fee, and total server-side
  4. Create the `Order` and its `OrderItem` rows with snapshotted values
  5. Register the confirmation email with `transaction.on_commit`
- Payment handoff **after** the transaction commits: COD returns the order, Khalti
  returns a `payment_url`
- `apps/orders/exceptions.py`: `EmptyCart` only. `VariantUnavailable` and
  `InsufficientStock` already exist in `apps/catalog/exceptions.py` and are
  raised by the catalog service — the app that owns the row owns the error.
  Import them; do not define a second pair
- A `checkout` throttle scope

---

## Implemented

- `apps/orders/serializers.py` — `CheckoutItemSerializer` and `CheckoutSerializer`
  (shape only, no queries, no price field), and `CheckoutResponseSerializer`
- `apps/orders/services.py::place_order` — owns the transaction, collapses
  duplicate cart lines, calls `decrement_variant_stock` once with the whole cart,
  resolves every price off the returned locked rows, computes the shipping fee and
  total server-side, and creates the order with its snapshotted lines
- `apps/orders/exceptions.py` — `EmptyCart` only, as specified
- `apps/orders/views.py::CheckoutView` and the `checkout/` route — `AllowAny`,
  POST only, `201` on success, the `checkout` throttle scope
- `config/settings/base.py` — `SHIPPING_FEE_INSIDE_VALLEY` (150.00),
  `SHIPPING_FEE_OUTSIDE_VALLEY` (250.00), `KATHMANDU_VALLEY_DISTRICTS`, and the
  `checkout` throttle rate at `30/hour`; `config/settings/test.py` carries its own
  `checkout` entry because that override replaces the rates dict
- `apps/catalog/services.py` — `decrement_variant_stock` now
  `select_related("product", "size", "color")`. See Gotchas
- `apps/orders/tests/test_checkout.py` — 25 tests

---

## Remaining

Two pieces of this document belong to features that do not exist yet. Both were
deliberately deferred rather than stubbed, and the seams for them are built and
tested:

- **The payment handoff is complete for both methods.** `CheckoutView` branches at
  the point after `place_order` commits, where ADR 0005 requires it: cash on
  delivery records what the courier will collect, Khalti initiates and returns a
  `payment_url`. When initiation fails the response is a 422
  `payment_gateway_unavailable` naming the order, because by then the order exists
  and holds stock — see `payments.md`.
- ~~`test_gateway_is_not_called_inside_transaction` was never written.~~ It exists
  now, in `apps/orders/tests/test_checkout.py`. It records the transaction nesting
  depth at the moment `requests.post` is called and compares it with the depth
  outside any service, so the rule ADR 0004 and ADR 0005 share is asserted rather
  than merely arranged. Depth rather than `in_atomic_block`, because `django_db`
  wraps every test in its own atomic block.
- ~~No confirmation email.~~ Landed with `transactional-email.md` (#9): the
  `transaction.on_commit` registration sits inside `place_order`, and the
  customer receives the `access_token` that under ADR 0003 is their only route
  back to the order. Pinned by `test_confirmation_is_sent_after_commit` and
  `test_confirmation_is_not_sent_when_transaction_rolls_back`.

Two smaller things, deliberately left:

- **There is no maximum cart size.** `items` has no `max_length`, so one request
  may carry thousands of lines, each becoming a key in the `pk__in` lookup and a
  row in the `bulk_create`, all inside the transaction that holds the row locks.
  The `checkout` throttle at `30/hour` bounds the rate but not the size of a single
  request. No limit was invented here because none is specified and the number is a
  product decision; it is the first thing to add if the endpoint is abused.
- **`decrement_variant_stock` writes each variant with its own `UPDATE`.** For a
  realistic cart that is one to five statements; a `bulk_update` would make it one.
  It belongs to `product-catalog.md` (#4), its tests are there, and changing it is
  not this feature's business — noted here because this is the caller that makes it
  visible.

---

## Decisions

### Decision: prices are re-resolved server-side and the client's are ignored

**Decision**

`CheckoutSerializer` does not accept a price field at all. Prices come from the
database inside the transaction.

**Reason**

A price in the request body is a price the customer can edit. Accepting one and
validating it against the database is strictly worse than not accepting it: it is
the same query plus an opportunity to get the comparison wrong.

**Consequence**

The storefront's displayed total can differ from the order total if the merchant
repriced mid-session. The response returns the authoritative total, and the
confirmation page shows it rather than the cart's figure.

### Decision: shipping is a flat fee from settings, by district band

**Decision**

Two bands — inside and outside the Kathmandu valley — as a settings value, resolved
from the submitted district.

The values are `150.00` inside and `250.00` outside, from
`SHIPPING_FEE_INSIDE_VALLEY` and `SHIPPING_FEE_OUTSIDE_VALLEY`. The valley is
Kathmandu, Lalitpur and Bhaktapur, matched case-insensitively.

**Reason**

The brand ships by courier at a flat negotiated rate. Carrier rate APIs, weight
bands, and zone tables model a complexity that does not exist yet.

**Consequence**

Changing the fee is a deploy, not an admin edit. `shipping_fee` is **stored** on the
order, so a later change does not alter historical totals.

### Decision: an unrecognised district pays the outside-valley fee

**Decision**

`district` is free text from the request body. Anything that is not one of the
three valley districts is charged the outside rate.

**Reason**

The two wrong answers are not symmetrical. Defaulting to the *inside* rate
undercharges every district the merchant has not enumerated — which is most of
Nepal — and the merchant absorbs the courier difference on orders they may never
look at. Defaulting to the *outside* rate is wrong only for a misspelled valley
district.

Validating `district` against a list instead would put all seventy-seven districts
of Nepal into the API contract and reject a customer over a spelling.

**Consequence**

A customer who types "Kathmandoo" is overcharged 100. The order is `pending` and
the merchant can see it before shipping, which is the recovery path. If this
happens in practice, the fix is a district dropdown in the storefront, not
server-side fuzzy matching.

### Decision: an unavailable variant fails the whole checkout

**Decision**

If any line cannot be satisfied, nothing is placed. There is no partial order.

**Reason**

A partial order means a customer paying for a subset of what they chose without
agreeing to it. The correct behaviour is to tell them what is unavailable and let
them decide.

**Consequence**

The 422 response must name the offending variant in `details`, or the storefront
cannot show a useful message.

---

## Gotchas

- **Lock in ascending `pk` order.** This single line prevents deadlock on
  multi-item carts. A future refactor that iterates the cart in submission order
  and locks as it goes reintroduces it, and the symptom is an intermittent 500 that
  never reproduces locally.
- **The Khalti call happens after commit, not inside the transaction.** Holding row
  locks across an external HTTP call is how one slow gateway response blocks every
  other buyer of the same variants.
- **The confirmation email is registered with `transaction.on_commit`**, never sent
  inline. An SMTP timeout inside the transaction rolls back a placed order. See
  [ADR 0006](../decisions/0006-transactional-email-sends-in-request-on-commit.md).
- The email carries the order's `access_token`, which under ADR 0003 is the
  customer's only route back to their order. A failed send is therefore worse here
  than in a store with accounts — and nothing retries it.
- Stock is decremented **before** payment. An abandoned redirect leaves stock held
  with no automatic release. This is accepted in ADR 0004 and creates a standing
  merchant duty described in `merchant-admin.md`.
- `select_for_update()` requires an open transaction. Outside `atomic()` it raises,
  and over Supabase's pooler the failure mode is worse than obvious.
- The serializer validates shape only. Checking stock in `validate()` is a
  check-then-act race — `convention.md` calls this out explicitly. Availability is
  decided inside the lock, not before it.
- **`decrement_variant_stock` selects `size` and `color`, not just `product`.**
  `place_order` snapshots the size and colour *names* onto each order line, and
  ADR 0007 made both foreign keys. Without the joins that is two queries per
  variant while the transaction holds every row lock in the cart — the one place
  in the system where an N+1 blocks other buyers rather than merely being slow.
  The lock is `of=("self",)`, so the extra joins do not widen it.
- **Duplicate cart lines for one variant are summed before the decrement.** The
  cart is a browser array and nothing stops it holding the same variant twice.
  `decrement_variant_stock` takes a `Mapping[UUID, int]`, so building it by
  assignment would decrement only the last line while charging for both.
  `cancel_order` sums for the mirror-image reason.
- **The concurrency test is meaningful, and was verified so.** With
  `select_for_update()` removed from `decrement_variant_stock`, both buyers receive
  `201` and the last unit sells twice.
- **`EmptyCart` is unreachable over HTTP**, and that is not a mistake.
  `CheckoutSerializer` declares `items` with `allow_empty=False`, so an empty cart
  is a 400 `validation_error` before the service sees it — which is what the Errors
  section promises. The service still guards its own precondition, because
  `place_order` is callable from the admin and the shell, where an empty cart would
  write an order with no lines and a zero total.
  `test_place_order_with_no_items_raises_empty_cart` calls the service directly.
- **Checkout costs one query per cart line, and exactly one.** That line is the
  stock `UPDATE`, which is inherent — N rows change, so N rows are written. The
  locked fetch, the order insert and the `bulk_create` of the lines are each one
  query whatever the cart holds.
  `test_each_extra_cart_line_costs_exactly_one_query` asserts the *growth* rather
  than a total, so it survives a savepoint change but still fails the moment the
  size and colour joins are dropped and the snapshot starts querying per variant.
- `place_order` is called as `place_order(**serializer.validated_data)`. The
  serializer's field names and the service's keyword arguments are therefore one
  contract; renaming a field without renaming the argument is a `TypeError` at
  runtime, not a type error at check time.

---

## API

### Endpoint

```text
POST /api/v1/checkout/
```

### Request

```json
{
  "items": [{ "variant_id": "...", "quantity": 1 }],
  "email": "customer@example.com",
  "phone": "98XXXXXXXX",
  "full_name": "...",
  "address_line": "...",
  "city": "...",
  "district": "...",
  "note": "",
  "payment_method": "khalti"
}
```

### Response

```json
{
  "order_number": "TL-2026-000142",
  "status": "pending",
  "subtotal": "4500.00",
  "shipping_fee": "150.00",
  "total": "4650.00",
  "payment_url": "https://pay.khalti.com/?pidx=..."
}
```

`payment_url` is present only for Khalti. For COD the order is returned without it.
The `access_token` is **not** in the response body — it reaches the customer only by
email.

`payment_url` is present only for Khalti; a cash-on-delivery response omits the key
rather than sending null.

### Errors

```json
{
  "error": {
    "code": "insufficient_stock",
    "message": "Not enough stock to fulfil this order.",
    "details": { "variant_id": "...", "available": 2, "requested": 3 }
  }
}
```

400 `validation_error` for a malformed body or an empty cart. 422
`variant_unavailable` for an unknown or unpublished variant. 422
`insufficient_stock` as above. 429 `throttled`.

---

## Data changes

None. `Order` and `OrderItem` are defined in `orders.md`.

---

## Permissions

`AllowAny`, declared explicitly. There is no authentication in Phase 1, so anyone
can place an order — which is the intent.

The security boundary here is not authentication, it is **input distrust**. Prices,
availability, and totals are all server-derived. The only things taken from the
request are the variant ids, the quantities, and the contact and address fields.

A dedicated `checkout` throttle scope limits order-placement abuse. Note that the
endpoint writes and holds locks, so it is more expensive to abuse than a read
endpoint.

---

## Tests

25 tests, all in `apps/orders/tests/test_checkout.py`:

- `test_checkout_creates_order_and_returns_201`
- `test_checkout_decrements_variant_stock`
- `test_checkout_ignores_client_supplied_price` — sends `unit_price`, `subtotal`
  and `total` in the body and asserts the server's figures win
- `test_checkout_snapshots_name_size_and_price_onto_items`
- `test_checkout_uses_the_variant_price_override_when_set`
- `test_checkout_beyond_available_stock_returns_422`
- `test_unavailable_line_places_no_order_at_all` — the all-or-nothing rule, and
  that the satisfiable line's stock did not move
- `test_unpublished_variant_returns_422`, `test_unknown_variant_returns_422`
- `test_empty_cart_returns_400`
- `test_zero_quantity_returns_400_not_500` — the `min_value=1` bound
- `test_duplicate_cart_lines_for_one_variant_are_summed`
- `test_shipping_fee_is_charged_by_district_band` — parametrised over a valley
  district, a differently-cased one, an outside one, and a misspelling
- `test_checkout_response_never_contains_access_token`
- `test_cod_checkout_records_a_pending_payment` — the handoff into `apps/payments`
- `test_khalti_checkout_returns_a_payment_url` and
  `test_cod_checkout_omits_the_payment_url`
- `test_a_failed_initiate_returns_422_naming_the_order`
- `test_an_unknown_payment_method_returns_400`
- `test_exceeding_checkout_throttle_returns_429`
- `test_place_order_with_no_items_raises_empty_cart` — the service directly, since
  the serializer answers first over HTTP
- `test_each_extra_cart_line_costs_exactly_one_query`
- `test_concurrent_checkout_for_last_unit_places_one_order` — two threads racing
  for one unit, expecting `[201, 422]`. `transaction=True`, and each thread closes
  its connection. Verified meaningful: with `select_for_update()` removed from
  `decrement_variant_stock`, both threads receive `201` and the unit sells twice
- **`test_gateway_is_not_called_inside_transaction`** — records the transaction
  nesting depth at the moment `requests.post` is called and compares it with the
  depth outside any service. Depth rather than `in_atomic_block`, because
  `django_db` wraps every test in its own atomic block and that flag is therefore
  true throughout. Verified meaningful: wrapping the view's `initiate_khalti_payment`
  call in `transaction.atomic()` makes it fail with `[2] == [1]`
- `test_a_failed_cod_record_leaves_an_order_with_no_payment` — the state
  `payments.md` documents and nothing asserted: `record_cod_payment` runs after the
  transaction commits, so its failure cannot roll the order back, and
  `PaymentAdmin` cannot create the missing row by hand

Both tests deferred by earlier features have now landed: the confirmation email as
`test_confirmation_is_sent_after_commit` in `apps/orders/tests/test_emails.py`
(#9), and the gateway one above (#8).

---

## Files

```text
apps/orders/
├── serializers.py
├── services.py
├── views.py
├── urls.py
├── exceptions.py
└── tests/
    └── test_checkout.py
apps/catalog/services.py         select_related on the locked variants
config/settings/base.py          shipping fees, valley districts, checkout rate
.env.example                     SHIPPING_FEE_*, DJANGO_THROTTLE_CHECKOUT
config/settings/test.py          its own checkout rate
```

No migration: `Order` and `OrderItem` were created by `orders.md` (#6).

---

## Future context

This document is a concurrency argument, not a schema. The three things that make
it correct are: locks in `pk` order, the external call outside the transaction, and
prices resolved inside the lock. Everything else is bookkeeping.

The server-side half of the cart lives here because the cart owns no table. If
Phase 2 adds a persisted cart — for abandoned-cart email, most likely — it becomes a
real model and probably a real app, and this endpoint changes from "validate a
payload" to "convert a row".

`test_gateway_is_not_called_inside_transaction` looks like an odd test. It is
guarding the constraint most likely to be broken by a well-meaning refactor that
moves the Khalti call "closer to where the order is created".
