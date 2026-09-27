# Checkout quote and shipping settings

Status: Implemented

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

- `KATHMANDU_VALLEY_DISTRICTS` in `config/settings/base.py` stays in code: it is
  geography, not pricing.
- The storefront performs no money arithmetic (its `CLAUDE.md`), so every figure it
  shows must come from this API.
- Existing orders store their own `subtotal`, `shipping_fee` and `total`, so changing
  the settings never rewrites a placed order.

---

## Implemented

### Model

- `apps/orders/models.py::ShippingSettings(TimeStampedModel)`, table
  `shipping_settings`: `inside_valley_fee`, `outside_valley_fee` (Decimal 10,2) and
  `free_shipping_threshold` (Decimal 10,2, nullable; null means no free shipping).
  The primary key is a `SmallIntegerField` defaulting to `SHIPPING_SETTINGS_ID = 1`
  (`apps/orders/constants.py`).
- Database constraints: `shipping_settings_singleton` (`id = 1`, so a second row
  cannot exist), `shipping_settings_fees_not_negative` (both fees ≥ 0) and
  `shipping_settings_threshold_positive` (threshold null or > 0).
- Migrations: `orders/0002_shipping_settings` creates the table;
  `orders/0003_default_shipping_settings` inserts the row with Rs 150 / Rs 250 and
  no threshold (`get_or_create`, reverse is a no-op).
- `apps/orders/selectors.py::get_shipping_settings()` returns the row.

### Pricing

- `apps/orders/services.py::price_cart(*, variants_by_id, quantities, district)`
  returns a frozen `CartPrice` (`subtotal`, `shipping_fee`, `discount`, `total`,
  `free_shipping_remaining`, `lines`) whose lines are `PricedLine`s (`variant_id`,
  `quantity`, `unit_price`, `line_total`). It reads the settings row and writes
  nothing.
  - `unit_price` is the variant's `price` (`price_override` or the product's
    `base_price`); `line_total = unit_price × quantity`; `subtotal` is their sum.
  - `shipping_fee` is `0.00` when a threshold is set and `subtotal >= threshold`.
    Otherwise it is `inside_valley_fee` when the stripped, lower-cased district is in
    `KATHMANDU_VALLEY_DISTRICTS`, and `outside_valley_fee` for any other district.
  - `free_shipping_remaining` is `threshold - subtotal` when that is above 0, and
    `None` when no threshold is set or it has been reached.
  - When `district` is `None`, `shipping_fee` and `total` are `None`, unless the
    threshold is reached, in which case `shipping_fee` is `0.00` and `total` is
    `subtotal`.
  - `discount` is always `0.00`; `total = subtotal - discount + shipping_fee`.
- `place_order` calls `price_cart` on the rows `decrement_variant_stock` has locked,
  inside the same transaction, and builds the order lines and totals from its
  result. Its behaviour is otherwise unchanged.
- `quote_cart(*, items, district)` raises `EmptyCart` for no items, sums duplicate
  lines exactly as `place_order` does (`_summed_quantities`), resolves the variants
  with `apps.catalog.services.check_variant_availability` (no lock, no write), and
  returns `price_cart(...)`.
- `apps/catalog/services/stock.py`: the availability rules (unknown, unpublished,
  inactive brand, shortfall) moved into shared helpers, so
  `check_variant_availability` and `decrement_variant_stock` raise the same
  `VariantUnavailable` and `InsufficientStock` with the same details.
- `update_shipping_settings(*, fields)` assigns the given fields and saves them with
  `updated_at`; it logs `shipping.settings_updated` with the field names.

### Endpoints

- `apps/orders/views.py::QuoteView` (`AllowAny`, scope `quote`),
  `ShippingSettingsView` (`AllowAny`, scope `catalog`); routes `checkout/quote/`
  (`v1:checkout-quote`) and `shipping/` (`v1:shipping`).
- `apps/backoffice/views.py::ShippingSettingsView(StaffAPIView)`, route
  `settings/shipping/` (`v1:admin-shipping-settings`).
- Serializers: `QuoteSerializer`, `QuoteResponseSerializer`, `QuoteLineSerializer`
  and `ShippingSettingsSerializer` in `apps/orders/serializers.py`;
  `AdminShippingSettingsSerializer` and `ShippingSettingsWriteSerializer` in
  `apps/backoffice/serializers.py`.

### Configuration

- `SHIPPING_FEE_INSIDE_VALLEY` and `SHIPPING_FEE_OUTSIDE_VALLEY` are removed from
  `config/settings/base.py`, `config/settings/test.py`, `.env.example`,
  `render.yaml` and `tests/test_settings.py`. `EnvironmentReader.decimal`, which only
  they used, is removed from `config/settings/strict_env.py`.
- `DJANGO_THROTTLE_QUOTE` (required, ADR 0008) sets the `quote` scope's rate in
  `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`: `600/hour` in `render.yaml` and
  `.env.example`, `1000/minute` in `config/settings/test.py`.

---

## Remaining

None.

---

## Decisions

### Decision: the singleton is enforced by the database

**Decision**

The row's primary key is fixed at 1 and a `CheckConstraint` rejects any other key.
The selector is a plain `get(pk=1)`; it never creates the row.

**Reason**

ADR 0017 requires exactly one row. The constraint makes a second row impossible, and
a selector that silently created a missing row would invent prices nobody chose,
which ADR 0008 exists to prevent.

### Decision: the quote shares checkout's availability rules, not its lock

**Decision**

`check_variant_availability` runs the same checks as `decrement_variant_stock` on
unlocked rows.

**Reason**

The quote must return the same errors as checkout (the storefront shows them in the
bag), but it must not hold row locks for a read that may never become an order.
Only the locked decrement decides; a quote can be stale by the time the customer
checks out.

### Decision: the quote has its own throttle scope

**Decision**

`POST /checkout/quote/` uses the `quote` scope (`DJANGO_THROTTLE_QUOTE`,
`600/hour`), not checkout's `checkout` scope (`30/hour`).

**Reason**

`ScopedRateThrottle` keys its counter by scope and client IP. On a shared scope,
a bag page that quotes on every quantity change would use up the customer's
allowance to place the order. The quote takes no lock and writes nothing, so it can
have a ceiling near browsing's (`catalog`, `600/hour`), while checkout keeps its low
one.

### Decision: a blank district is no district

**Decision**

`district` may be absent, `null` or `""` on the quote; all three price without a
district.

**Reason**

Forms submit empty strings. Treating `""` as a district would charge the
outside-valley fee to a customer who has not said where they live.

---

## Gotchas

- The quote and checkout have separate throttle counters (`quote` and `checkout`).
  Quoting never uses up the checkout allowance, and a customer throttled on quotes
  can still check out. `test_quotes_do_not_consume_the_checkout_allowance` guards
  this.
- `GET /shipping/` sets no `Cache-Control` header, like the catalogue endpoints.
  "Cacheable" means it holds no per-visitor data, so the storefront may cache it;
  the API itself caches nothing (`architecture.md`).
- A transactional test (`transaction=True`) flushes every table afterwards, which
  deletes the migration's row for later transactional tests. Such tests request the
  `shipping_settings` fixture in the root `conftest.py`, which recreates it.
  `serialized_rollback` does not work here: it collides with existing content types.
- `place_order` passes `cast(Decimal, …)` for `shipping_fee` and `total`: checkout
  always has a district, so `price_cart` always sets both.
- An empty `PATCH` body is a `200` that only bumps `updated_at`.

---

## API

### `POST /api/v1/checkout/quote/`

Public, throttle scope `quote` (`DJANGO_THROTTLE_QUOTE`, `600/hour`), separate from
checkout's. It writes nothing and sends no email.

```json
{ "items": [{ "variant_id": "…", "quantity": 2 }], "district": "Lalitpur" }
```

`district` is optional (absent, `null` or `""`); the bag page quotes without one.
`items` is validated exactly like checkout's (`allow_empty=False`, `quantity ≥ 1`).
Duplicate lines for one variant are summed into one line.

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

Without a district and below the threshold, `shipping_fee` and `total` are `null`.

Errors are identical to `POST /checkout/`: `400 validation_error`,
`422 variant_unavailable`, `422 insufficient_stock` and `429 throttled` (here from
the `quote` scope).

### `GET /api/v1/shipping/`

Public, `catalog` throttle scope, no per-visitor data.

```json
{ "inside_valley_fee": "150.00", "outside_valley_fee": "250.00", "free_shipping_threshold": "8000.00" }
```

`free_shipping_threshold` is `null` when the merchant hasn't set one.

### `GET, PATCH /api/v1/admin/settings/shipping/`

Staff only, the same policy as the other admin routes (`StaffAPIView`). It uses the
same fields as the public endpoint, plus `updated_at`:

```json
{ "inside_valley_fee": "150.00", "outside_valley_fee": "250.00",
  "free_shipping_threshold": null, "updated_at": "2026-09-27T05:07:00.361445Z" }
```

`PATCH` is partial. Validation: both fees must be ≥ 0 (not null) and the threshold
must be ≥ 0.01 or `null`, otherwise `400 validation_error` naming the field. `null`
switches free shipping off. The write goes through `update_shipping_settings`, per
ADR 0002. Anonymous `401`, non-staff `403`.

### `POST /api/v1/checkout/` response

Unchanged. The placed order's figures now come from `price_cart`, so they equal what
the quote said for the same cart and district, as long as prices and settings haven't
changed in between.

---

## Data changes

- A new `shipping_settings` table, containing one row.
- `orders/0003_default_shipping_settings` creates that row.
- No change to `order`.

---

## Permissions

The quote and `/shipping/` are `AllowAny`. The settings read and write require an
active staff JWT (`StaffAPIView`).

---

## Tests

- `apps/orders/tests/test_pricing.py` — `price_cart`: the valley and outside-valley
  fees (including padding and case); line totals and zero discount; no threshold;
  the threshold boundary (7999.99, 8000.00, 8000.01 against 8000.00);
  `district=None` below and at the threshold; fees read from the row.
- `apps/orders/tests/test_quote.py` — the documented response; no district as
  absent, `null` and `""`; duplicate lines summed; quote totals equal a checkout
  placed with the same body, across thresholds and bands; it writes nothing (stock,
  orders and outbox unchanged); client prices ignored; `400` for empty, malformed
  and missing items and zero quantity; `422 variant_unavailable` for unpublished,
  inactive-brand and unknown variants; `422 insufficient_stock` without `available`;
  the `quote` throttle, and quotes not consuming the `checkout` counter; `/shipping/` values, null threshold and `catalog`
  throttle.
- `apps/backoffice/tests/test_shipping_settings.py` — GET shape; partial PATCH;
  `null` threshold; zero fee allowed; negative fees, zero/negative threshold, null
  fee and non-numbers are `400`; non-staff `403` leaves the row alone; a PATCH
  changes the next quote. `test_permissions.py` covers the route's 401/403 and
  `StaffAPIView` automatically.
- `apps/orders/tests/test_models.py` — the migration's default row; a second row and
  negative fees or a zero threshold violate the constraints.
- `tests/test_settings.py` — the parity tests no longer expect the two variables.
- Existing checkout tests (bands, totals, query count, concurrency) pass unchanged
  through `price_cart`.

---

## Files

```text
apps/orders/constants.py                               SHIPPING_SETTINGS_ID
apps/orders/models.py                                  ShippingSettings
apps/orders/migrations/0002_shipping_settings.py
apps/orders/migrations/0003_default_shipping_settings.py
apps/orders/selectors.py                               get_shipping_settings
apps/orders/services.py                                price_cart, quote_cart, update_shipping_settings
apps/orders/{serializers,views,urls}.py                quote and /shipping/
apps/catalog/services/stock.py                         check_variant_availability
apps/backoffice/{serializers,views,urls}.py            admin settings route
config/settings/{base,test,strict_env}.py, .env.example, render.yaml   quote rate, fees removed
conftest.py                                            shipping_settings fixture
```

---

## Future context

Discount codes and sale prices plug into `price_cart`: `discount` is already in the
response and in the total. Nothing else may compute money (ADR 0017).
