# ADR 0017: Shipping fees are merchant data

Status: Accepted

Date: 2026-09-27

Supersedes: the `SHIPPING_FEE_*` entries of [ADR 0008](0008-every-environment-variable-is-required.md)

---

## Context

The two shipping fees were environment variables. Changing one meant editing Render's
settings and redeploying. The storefront repeated them in prose, in
`NEXT_PUBLIC_SHIPPING_NOTE`, which had to be updated by hand and then redeployed. The
merchant now also wants a free-shipping threshold, and would like to switch it on or
off for promotions.

---

## Decision

The fees and the threshold live in a single-row `ShippingSettings` table. Staff edit
them through the admin API, and the storefront reads them from
`GET /api/v1/shipping/`. The env vars are removed. The valley district list stays in
code, because it describes geography, not pricing.

---

## Reason

Prices are merchant data. A table gives the merchant control, gives the storefront
one source for its copy, and keeps the fee inside the same pricing function that
checkout uses.

---

## Alternatives considered

### Keep the env vars and add a third for the threshold

Why it was not chosen: a promotion would still need a deploy, and the storefront copy
would still be duplicated.

---

## Consequences

### Positive

- The merchant changes shipping without a deploy.
- Storefront copy can't drift from the real fees.

### Negative

- One more table, which must always hold exactly one row.

### Constraints introduced

- Every fee calculation goes through `price_cart`. Nothing else reads the settings to
  compute money.

---

## Implementation

```text
apps/orders/models.py                        ShippingSettings (one row, id = 1)
apps/orders/migrations/0003_default_shipping_settings.py
apps/orders/services.py                      price_cart, quote_cart, update_shipping_settings
apps/orders/selectors.py                     get_shipping_settings
apps/orders/views.py                         /checkout/quote/, /shipping/
apps/backoffice/views.py                     /admin/settings/shipping/
config/settings/base.py                      SHIPPING_FEE_* removed
render.yaml, .env.example, config/settings/test.py
docs/features/checkout-quote-and-shipping.md
```
