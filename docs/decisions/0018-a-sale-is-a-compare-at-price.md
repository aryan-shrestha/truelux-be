# ADR 0018: A sale is a compare-at price

Status: Accepted

Date: 2026-09-29

Supersedes: None

---

## Context

The merchant wants to show products on sale, with the old price struck through.
There are two common models:

- store a "was" price and let the current price be what it already is;
- store a sale price or percentage that overrides the current price, often with
  dates.

---

## Decision

A sale is expressed as `ProductVariant.compare_at_price`, the "was" price. What
the customer pays is still the variant's resolved `price` (`price_override`,
falling back to `base_price`). A variant is on sale while its compare-at is
above its price. The API derives `on_sale` and `discount_percent`, and the
storefront never computes them.

---

## Reason

- Checkout, the quote and every order snapshot already price from
  `variant.price`, so this adds no second price path that could disagree with
  the charge.
- The merchant runs a sale by lowering the price and entering the old one,
  the same two fields every mainstream shop platform uses.
- The compare-at is display-only, so a stale or wrong one can mislabel a
  product but can never change what anyone is charged.

---

## Alternatives considered

### A `sale_price` that overrides the price

Why it was not chosen: it would be a third source of truth beside
`base_price` and `price_override`, and checkout, the quote and order snapshots
would all have to learn it.

### Percentage sales with start and end dates

Why it was not chosen: that is a campaign feature, and it overlaps discount
codes (Increment 3). It can be layered on later by setting and clearing
compare-at prices on a schedule.

---

## Consequences

### Positive

- Pricing stays single-sourced.

### Negative

- Ending a sale is two edits: raise the price back and clear the compare-at.
  If the merchant forgets the second, nothing breaks, because a compare-at at or
  below the price is simply not a sale.

### Constraints introduced

- The compare-at never enters `price_cart`.
- "Above the price" is checked in the services, because the database cannot
  compare against the product's `base_price`.

---

## Implementation

```text
apps/catalog/models.py
apps/catalog/services/products.py
apps/catalog/selectors.py
apps/catalog/serializers.py
apps/catalog/filters.py
apps/catalog/workbook/
```
