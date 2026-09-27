# Checkout quote and shipping settings

Status: Planned

Last updated: 2026-09-27

---

## Goal

Let customers see their subtotal, shipping and total before placing an order, and let
the merchant change shipping fees and set a free-shipping threshold without a
deploy. This is the pricing foundation for sale prices and discount codes (Phase 2).

---

## Scope

What is included in this implementation?

- A `ShippingSettings` singleton: inside-valley fee, outside-valley fee, and an
  optional free-shipping threshold
- One pricing function, `price_cart`, used by both the quote and `place_order`, so
  the two can never disagree
- `POST /api/v1/checkout/quote/`: prices a cart without writing anything
- `GET /api/v1/shipping/`: the public fees and threshold, for storefront copy
- `GET/PATCH /api/v1/admin/settings/shipping/`: the merchant edits them
- The `SHIPPING_FEE_INSIDE_VALLEY` and `SHIPPING_FEE_OUTSIDE_VALLEY` env vars are
  retired ([ADR 0017](../decisions/0017-shipping-fees-are-merchant-data.md))

What is explicitly outside the scope?

- Per-district fees beyond the existing valley and outside-valley split
- Weight-based or courier-quoted shipping
- Discounts. The quote returns `discount: "0.00"` so the shape is ready for them.

---

## Context

- `place_order` in `apps/orders/services.py` prices lines from the rows that
  `decrement_variant_stock` locks, and `_shipping_fee_for(district)` reads the two
  env settings. `KATHMANDU_VALLEY_DISTRICTS` in `config/settings/base.py` stays in
  code.
- The storefront performs no money arithmetic (its `CLAUDE.md`), so every figure it
  shows must come from this API.
- Existing orders store their own `subtotal`, `shipping_fee` and `total`, so changing
  the settings never rewrites a placed order.

---

## Planned

### Model

- `ShippingSettings(TimeStampedModel)` in `apps/orders/models.py`: `inside_valley_fee`
  and `outside_valley_fee` (Decimal ≥ 0), and `free_shipping_threshold` (Decimal > 0,
  nullable, where null means no free shipping). A singleton: one row with a fixed
  primary key, and a `get_shipping_settings()` selector that returns it.
- A data migration creates the row with Rs 150 / Rs 250 and no threshold, the
  values `render.yaml` carries today. The env vars are then removed from
  `base.py`, `.env.example`, `render.yaml`, `config/settings/test.py` and the
  parity tests.

### Pricing

- `price_cart(*, variants_by_id, quantities, district) -> CartPrice` is a pure
  function. It takes resolved variants and returns `subtotal`, `shipping_fee`,
  `discount` (always 0 for now), `total`, `free_shipping_remaining` and priced lines.
  - `shipping_fee` is 0 when a threshold is set and `subtotal >= threshold`.
    Otherwise it is the fee for the district, using the existing
    valley/outside rule.
  - `free_shipping_remaining` is `threshold - subtotal` when that is above 0, and
    `null` when no threshold is set or it has been reached.
  - When `district` is `None`, `shipping_fee` and `total` are `None`, unless the
    threshold is reached, in which case `shipping_fee` is `0.00` and `total` is
    `subtotal`.
- `place_order` calls `price_cart` on the rows it has locked. Its behaviour is
  otherwise unchanged.
- `quote_cart(*, items, district)` resolves the variants **without locks** and
  raises the same `EmptyCart`, `VariantUnavailable` and `InsufficientStock` errors
  as checkout, then returns `price_cart(...)`.

---

## API

### `POST /api/v1/checkout/quote/`

Public, throttle scope `checkout`. It writes nothing and sends no email.

```json
{ "items": [{ "variant_id": "…", "quantity": 2 }], "district": "Lalitpur" }
```

`district` is optional; the bag page quotes without one.

`200`:

```json
{
  "subtotal": "6400.00",
  "shipping_fee": "150.00",
  "discount": "0.00",
  "total": "6550.00",
  "free_shipping_remaining": "1600.00",
  "lines": [
    { "variant_id": "…", "quantity": 2, "unit_price": "3200.00", "line_total": "6400.00" }
  ]
}
```

Errors are identical to `POST /checkout/`: `400 validation_error`,
`422 variant_unavailable`, `422 insufficient_stock` and `429 throttled`.

### `GET /api/v1/shipping/`

Public, `catalog` throttle scope, cacheable.

```json
{ "inside_valley_fee": "150.00", "outside_valley_fee": "250.00", "free_shipping_threshold": "8000.00" }
```

`free_shipping_threshold` is `null` when the merchant hasn't set one.

### `GET, PATCH /api/v1/admin/settings/shipping/`

Staff only, the same policy as the other admin routes (`StaffAPIView`). It uses the
same fields as the public endpoint, plus `updated_at`. Validation: both fees must be
≥ 0 and the threshold must be > 0 or null, otherwise `400 validation_error`. The write
goes through an `update_shipping_settings` service, per ADR 0002.

### `POST /api/v1/checkout/` response

Unchanged. The placed order's figures now come from `price_cart`, so they equal what
the quote said for the same cart and district, as long as prices and settings haven't
changed in between.

---

## Data changes

- A new `shipping_settings` table, containing one row.
- A data migration creates that row.
- No change to `order`.

---

## Permissions

The quote and `/shipping/` are public. The settings write requires staff.

---

## Tests

To be written:

- `price_cart`:
  - the valley and outside-valley fees;
  - the threshold boundary (just below, exactly at, above);
  - no threshold set;
  - `district=None`, both below and above the threshold.
- The quote:
  - its figures equal the figures of a checkout placed with the same body;
  - it writes nothing (stock and order count unchanged);
  - each error code;
  - the throttle.
- The admin:
  - GET and PATCH;
  - validation;
  - non-staff gets 403;
  - a PATCH changes the next quote.
- The settings and blueprint parity tests no longer expect the two env vars.
