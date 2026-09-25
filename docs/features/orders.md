# Orders

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Own the record of what a customer bought, where it is going and where it is in
fulfilment, let the customer look it up again without an account, and let staff move
it through its lifecycle.

---

## Scope

What is included in this implementation?

- `Order` and `OrderItem`, with the address denormalised onto the order
- A human-readable order number and an opaque access token
- The status lifecycle `pending → confirmed → shipped → delivered`, with `cancelled`
  from `pending` or `confirmed`, and the services that move it
- `GET /api/v1/orders/{access_token}/` and the throttled order-number lookup
- Line items that snapshot product name, size, shade, SKU and price

What is explicitly outside the scope?

- Order creation (`checkout.md`), payments (`payments.md`), emails
  (`transactional-email.md`), the staff API (`admin-api.md`)
- Returns, refunds, partial cancellation, editing lines, customer accounts

---

## Context

[ADR 0003](../decisions/0003-guest-checkout-with-opaque-order-access-tokens.md): no
`user` foreign key; authorization is the unguessable `access_token` delivered by
email. [ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md): a
pending order holds stock until someone confirms or cancels it.
[ADR 0011](../decisions/0011-cash-on-delivery-only.md): `paid` became `confirmed`,
set after the merchant confirms by phone. ADR 0002: every transition is a service,
and `status` is read-only in the Django admin.

---

## Implemented

- `apps/orders/models.py` — `Order` and `OrderItem` (see Data changes).
- `apps/orders/constants.py` — `OrderStatus`, `PaymentMethod` (`cod` only),
  `ALLOWED_TRANSITIONS`, and the order-number prefix (`TL`), sequence and width.
- `apps/orders/services.py` — `generate_order_number`, `place_order`,
  `confirm_order`, `mark_order_shipped` (registers the shipping email on commit),
  `mark_order_delivered`, `cancel_order` (locks the order, restores stock through
  `restore_variant_stock`), and `transition_order`, which dispatches a target status
  to the matching service for the admin API.
- `apps/orders/selectors.py` — `get_order_by_access_token`,
  `get_order_by_number_and_email`, both prefetching `items`.
- `apps/orders/views.py`, `urls.py` — `OrderDetailView` and `OrderLookupView`
  (`AllowAny`; the lookup uses the `order_lookup` scope, `20/hour`) and `CheckoutView`.
- `apps/orders/admin.py` — `OrderAdmin` with read-only `status` and actions
  **Mark selected orders as confirmed / shipped / delivered**, **Cancel selected
  orders and return their stock**, and the two email resends.

---

## Remaining

- **Nothing constrains an order to one row per variant.** `place_order` merges
  duplicate cart lines and `cancel_order` sums per variant, so both are correct
  either way.

---

## Decisions

### Decision: the address and line details are snapshots

**Decision**

Address columns live on `order`; `product_name`, `variant_size`, `variant_shade`,
`sku` and `unit_price` live on `order_item`.

**Reason**

An order must read the same after a product, size or shade is renamed or retired.

### Decision: `order_number` comes from a Postgres sequence

**Decision**

`TL-<year>-<6 digits>` from `nextval('order_number_seq')`, created by `RunSQL` in
`0001_initial`. The year does not reset the counter.

**Reason**

`nextval()` cannot hand one number to two concurrent checkouts, unlike
`MAX(...) + 1`.

### Decision: a confirmed order can still be cancelled

**Decision**

`cancel_order` accepts `pending` and `confirmed`; it raises `OrderAlreadyShipped`
for `shipped`/`delivered` and `OrderNotCancellable` for `cancelled`.

**Reason**

Under COD nothing has been paid before delivery, so cancelling a confirmed order only
returns stock.

---

## Gotchas

- **`access_token` is a bearer credential.** It is never logged, never serialised,
  and absent from every Django admin list, search and fieldset.
- Both public lookups return an identical 404 for "no such order" and "wrong email".
- `order_number` gaps are normal: `nextval()` does not roll back.
- `cancel_order` locks the order row first, then the variants in ascending `pk`
  through `restore_variant_stock`. Anything that locks a variant before its order
  reintroduces the deadlock ADR 0004 warns about.
- `transition_order` does not consult `ALLOWED_TRANSITIONS`; each service guards its
  own move. A test asserts the map and the services agree for every pair.
- `OrderItem.quantity` is an `IntegerField` so the named `>= 1` constraint is the only
  check on the column.

---

## API

### `GET /api/v1/orders/{access_token}/` and `POST /api/v1/orders/lookup/`

Lookup body: `{ "order_number": "TL-2026-000142", "email": "customer@example.com" }`.

```json
{
  "order_number": "TL-2026-000142",
  "status": "shipped",
  "placed_at": "2026-09-20T10:14:00Z",
  "email": "customer@example.com",
  "phone": "98XXXXXXXX",
  "shipping": { "full_name": "…", "address_line": "…", "city": "…", "district": "…" },
  "items": [
    { "product_name": "Silk Foundation", "variant_size": "30 ml",
      "variant_shade": "Warm Beige", "sku": "LUM-SF-30ML-WB", "quantity": 1,
      "unit_price": "3200.00" }
  ],
  "subtotal": "3200.00",
  "shipping_fee": "150.00",
  "total": "3350.00",
  "payment_method": "cod"
}
```

`variant_shade` is `""` for a shadeless variant. Errors: `404 not_found`,
`429 throttled`.

---

## Data changes

**`order`** — `order_number` (unique), `access_token` (UUID, unique), `status`
(`pending`, `confirmed`, `shipped`, `delivered`, `cancelled`), contact and address
columns, `note`, `subtotal`, `shipping_fee`, `total`, `payment_method`. Index on
`(status, -created_at)`; checks `order_total_not_negative` and
`order_status_valid`.

**`order_item`** — `order` (`CASCADE`), `variant` (`PROTECT`), `quantity`,
`unit_price`, `product_name`, `variant_size`, `variant_shade` (blank allowed),
`sku`. Check `order_item_quantity_positive`.

Migrations were regenerated as a fresh `0001_initial`, which also creates
`order_number_seq`.

---

## Permissions

The two public endpoints are `AllowAny`; possession of the token, or the order number
together with its email, is the authorization. Staff reach orders through
`/api/v1/admin/orders/` and the Django admin.

---

## Tests

- `apps/orders/tests/test_api.py` — detail by token, wrong token 404, no token in the
  body, lookup by number and email (case-insensitive), identical 404s, throttle,
  constant query counts.
- `apps/orders/tests/test_services.py` — each transition, illegal transitions leave
  the status alone, cancellation restores stock once under concurrency.
- `apps/orders/tests/test_models.py` — constraints and `PROTECT`.
- `apps/orders/tests/test_admin.py` — the admin actions and read-only fields.
- `apps/backoffice/tests/test_orders.py` — the admin API and
  `ALLOWED_TRANSITIONS` agreeing with the services.

---

## Files

```text
apps/orders/
├── admin.py
├── constants.py
├── emails.py
├── exceptions.py
├── models.py
├── selectors.py
├── serializers.py
├── services.py
├── urls.py
├── views.py
└── tests/
```
