# Checkout

Status: Implemented

Last updated: 2026-09-27

---

## Goal

Turn a cart held in the customer's browser into a durable cash-on-delivery order,
without trusting anything the browser says about prices or availability, and without
two simultaneous buyers claiming the same last item.

---

## Scope

What is included in this implementation?

- `POST /api/v1/checkout/`: validate a submitted cart and place an order
- Server-side re-resolution of every price and every stock level
- Shipping fee calculation by district band, through `price_cart`
  (`checkout-quote-and-shipping.md`)
- The transaction boundary, the lock protocol and the lock ordering
- Snapshotting name, size, shade, SKU and price onto order lines
- Recording the cash-on-delivery payment

What is explicitly outside the scope?

- The `Order` and `OrderItem` models (`orders.md`) and payments (`payments.md`)
- Server-side carts: the cart lives in the browser
- Online payment, discount codes, gift cards, tax, address validation

---

## Context

There is no cart table. The storefront submits variant ids and quantities, and
everything in that payload is attacker-controlled.
[ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md) governs:
stock is decremented here, at placement, under `select_for_update()` on every
variant in the cart, **in ascending `pk` order**, so two carts cannot deadlock.
[ADR 0003](../decisions/0003-guest-checkout-with-opaque-order-access-tokens.md): there
is no authenticated user; contact details come from the body.
[ADR 0011](../decisions/0011-cash-on-delivery-only.md): `payment_method` must be
`cod`.

---

## Implemented

- `apps/orders/serializers.py` — `CheckoutItemSerializer` (`variant_id`,
  `quantity` with `min_value=1`) and `CheckoutSerializer` (shape only, no queries, no
  price field, `payment_method` limited to `PaymentMethod.choices`);
  `CheckoutResponseSerializer` (`order_number`, `status`, `subtotal`,
  `shipping_fee`, `total`).
- `apps/orders/services.py::place_order` — collapses duplicate lines, calls
  `apps.catalog.services.decrement_variant_stock` once for the whole cart, prices
  the returned locked rows with `price_cart` (the same function the quote uses, so
  a quote and the order it becomes agree), creates the order and its lines, and
  registers the confirmation email with `transaction.on_commit`.
- `apps/catalog/services/stock.py::decrement_variant_stock` — locks with
  `select_for_update(of=("self",))`, `select_related("product__brand", "size",
  "shade")`, ordered by `pk`; raises `VariantUnavailable` for unknown variants and
  for variants of an unpublished product or an inactive brand, and
  `InsufficientStock` without revealing the remaining count.
- `apps/orders/views.py::CheckoutView` — `AllowAny`, `checkout` throttle scope,
  calls `place_order` then `record_cod_payment`, returns `201`.
- The fees and the free-shipping threshold are the `ShippingSettings` row (default
  150.00 / 250.00, no threshold), edited by staff, not settings
  ([ADR 0017](../decisions/0017-shipping-fees-are-merchant-data.md)). Settings:
  `KATHMANDU_VALLEY_DISTRICTS`, `DJANGO_THROTTLE_CHECKOUT` (`30/hour`; the quote
  has its own `quote` scope).

---

## Remaining

- **There is no maximum cart size.** `items` has no `max_length`; the throttle bounds
  the rate but not the size of one request. The limit is a product decision.

---

## Decisions

### Decision: prices are re-resolved server-side and the client's are ignored

**Decision**

The serializer has no price field; every unit price comes from the locked variant's
`price` property (`price_override` or the product's `base_price`).

**Reason**

A price in the request body is a price the customer can edit.

### Decision: shipping is a flat fee by district band, and unknown districts pay the outside rate

**Decision**

Kathmandu, Lalitpur and Bhaktapur pay the inside-valley fee; every other string pays
the outside-valley fee, unless the subtotal reaches the free-shipping threshold, in
which case the fee is 0. The fee is stored on the order.

**Reason**

Overcharging a misspelt valley district is preferable to undercharging every
district nobody thought of. Storing it means a later fee change never rewrites a
historical total.

### Decision: an unavailable variant fails the whole checkout

**Decision**

One unavailable or short line rejects the cart with a 422; no partial order is
placed.

**Reason**

A partial order the customer did not ask for is worse than a clear error they can
fix in the cart.

---

## Gotchas

- `quantity`'s `min_value=1` is load-bearing: `decrement_variant_stock` raises a plain
  `ValueError` on a non-positive quantity, which would otherwise be a 500.
- `record_cod_payment` runs after `place_order` has committed; if it fails, the order
  exists without a payment row and the customer sees a 500.
- `InsufficientStock` details carry `variant_id` and `requested`, never `available`:
  checkout is public and would otherwise enumerate inventory.

---

## API

### `POST /api/v1/checkout/`

```json
{
  "items": [{ "variant_id": "uuid", "quantity": 2 }],
  "email": "sita@example.com",
  "phone": "98XXXXXXXX",
  "full_name": "Sita Sharma",
  "address_line": "Jhamsikhel",
  "city": "Lalitpur",
  "district": "Lalitpur",
  "note": "",
  "payment_method": "cod"
}
```

`201`:

```json
{ "order_number": "TL-2026-000123", "status": "pending", "subtotal": "3200.00",
  "shipping_fee": "150.00", "total": "3350.00" }
```

Errors: `400 validation_error` (shape, empty cart, zero quantity, any
`payment_method` but `cod`); `422 variant_unavailable`; `422 insufficient_stock`;
`429 throttled`.

---

## Data changes

None beyond `orders.md` and `payments.md`.

---

## Permissions

`AllowAny`. The boundary is input distrust, not identity.

---

## Tests

`apps/orders/tests/test_quote.py` proves a checkout's totals equal the quote's.
`apps/orders/tests/test_checkout.py`: order creation and stock decrement; client
prices ignored; name, size, shade and price snapshots, and `""` for a shadeless
variant; `price_override`; shortfalls, unpublished, inactive-brand and unknown
variants are 422 and place nothing; empty cart and zero quantity are 400; duplicate
lines are summed; shipping bands; no `access_token` in the response; a pending COD
payment is recorded; an unknown payment method is 400; the throttle; one extra query
per cart line; two concurrent buyers of the last unit place one order.

---

## Files

```text
apps/orders/{serializers,services,views,urls}.py   place_order, price_cart
apps/catalog/services/stock.py
apps/payments/services.py
apps/orders/tests/test_checkout.py
```
