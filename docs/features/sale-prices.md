# Sale prices

Status: Planned

Last updated: 2026-09-29

---

## Goal

Let the merchant put products on sale by showing what the customer saves: a
"was" price struck through beside the price they pay. Customers can then find
everything on sale in one place.

---

## Scope

What is included in this implementation?

- `ProductVariant.compare_at_price`: the "was" price, per variant, optional
- A variant is **on sale** when `compare_at_price` is set and greater than its
  resolved `price`. A product is on sale when any published variant is on sale
- Public API:
  - `compare_at_price`, `on_sale` and `discount_percent` on each variant
  - `on_sale`, `sale_price`, `compare_at_price` and `discount_percent` on product
    list and detail items
  - A `?on_sale=true` filter on the product list
- Admin API: `compare_at_price` on variant read and write, an on-sale flag on
  product list items, and a `?on_sale=true` filter
- The Excel workbook gains a **Compare-at price (NPR)** column on the Variants
  sheet, handled by both import and export
- `seed_demo` puts a handful of demo products on sale
- [ADR 0018](../decisions/0018-a-sale-is-a-compare-at-price.md)

What is explicitly outside the scope?

- Scheduled sales with start or end dates. The merchant sets and clears the
  price by hand.
- Discount codes (Phase 2, Increment 3)
- Changing what the customer pays. Checkout already charges the variant's
  resolved `price`; `compare_at_price` is display-only and never enters
  `price_cart`.

---

## Context

- `ProductVariant.price` is a property: `price_override`, falling back to
  `Product.base_price`. That is what checkout charges, and it is unchanged.
- The product list shows `base_price` and filters price bands on it. That stays
  as it is: `min_price` and `max_price` still read `base_price`.
- Money is a decimal string on the wire (`architecture.md`). The storefront
  must never compute a percentage, so `discount_percent` comes from the API.

---

## Planned

### Model

- `compare_at_price = DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)`
  on `ProductVariant`.
- `CheckConstraint product_variant_compare_at_positive`: null, or greater than 0.
  "Greater than the price" cannot be a database constraint, because the price can
  come from `Product.base_price`. It is enforced in the services instead:
  - **Writing a variant** (`create_variant`, `update_variant`) with a
    `compare_at_price` that is not greater than the variant's resolved price
    raises `CompareAtNotAbovePrice`: `400 validation_error` on
    `compare_at_price`, the same way field errors surface through the handler.
  - **Changing a product's `base_price` or a variant's `price_override`** so that
    an existing compare-at is no longer above the price is **allowed**. That
    variant simply stops being on sale. Rejecting the price change would block
    ordinary repricing.

### Read model

- A variant's `on_sale` is `compare_at_price is not None and compare_at_price > price`.
- `discount_percent` is `floor((compare_at_price - price) / compare_at_price * 100)`
  as an integer, and `null` when the variant is not on sale. Flooring means the
  badge never overstates the saving.
- For the product, the **sale variant** is the on-sale variant with the lowest
  resolved price, with ties broken by size `sort_order`:
  - `on_sale`: true if a sale variant exists.
  - `sale_price`: the sale variant's `price`, or `null`.
  - `compare_at_price`: the sale variant's `compare_at_price`, or `null`.
  - `discount_percent`: the sale variant's percent, or `null`.
- Computed with an annotation or `Subquery` in the list selector, so it adds no
  query per product. The list's tested query count must not grow.
- `?on_sale=true` uses the same predicate at the database level. Anything other
  than `true` or `false` is `400 validation_error`.

---

## API

### Product list item and detail add

```json
"on_sale": true,
"sale_price": "2720.00",
"compare_at_price": "3200.00",
"discount_percent": 15
```

The last three are `null` when `on_sale` is false. `base_price` is unchanged.

### Variant adds

```json
{ "id": "…", "price": "2720.00", "compare_at_price": "3200.00", "on_sale": true, "discount_percent": 15, "…": "…" }
```

A variant with a compare-at at or below its price returns that value in
`compare_at_price`, but `on_sale` is false and `discount_percent` is `null`.

### `GET /api/v1/products/?on_sale=true`

Returns only products with at least one on-sale published variant. It can be
combined with every other filter and ordering.

### Admin

- Variant read and write gain `compare_at_price`, which is nullable. A value
  that is not above the variant's price is `400 validation_error` on
  `compare_at_price`.
- Admin product list items gain `on_sale`. `GET admin/products/?on_sale=true`
  filters on it.

---

## Data changes

- A nullable `product_variant.compare_at_price` column with a positive check.
- New migration.

---

## Permissions

Reads are public. Writes are staff-only, through the admin API.

---

## Tests

To be written:

- The on-sale predicate against both an override price and a base price.
- A compare-at equal to the price is not on sale.
- `discount_percent` flooring (3200 → 2720 is 15; 999 → 850 is 14).
- Choosing the sale variant: the lowest price wins, and ties go to size order.
- `?on_sale=true` and `?on_sale=false`, and combined with brand and category.
- An invalid `on_sale` value is 400.
- The list query count is unchanged.
- The service rejects a compare-at that is not above the price.
- Repricing above an existing compare-at is allowed and ends the sale.
- The admin API round-trips `compare_at_price`.
- Checkout still charges `price` (the compare-at never reaches `price_cart`).
- A workbook round trip with the new column, and a bad compare-at reported
  with its sheet, row and column.
