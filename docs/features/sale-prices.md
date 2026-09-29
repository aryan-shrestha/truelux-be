# Sale prices

Status: Implemented

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

## Implemented

- `apps/catalog/models.py` — `ProductVariant.compare_at_price` (nullable
  `DecimalField(10, 2)`) with `CheckConstraint product_variant_compare_at_positive`;
  the `on_sale` and `discount_percent` properties; and the module function
  `discount_percent(*, price, compare_at_price)`, the one implementation of the
  percentage (`int((compare_at - price) * 100 // compare_at)`, `None` unless on sale).
- `apps/catalog/migrations/0003_compare_at_price.py` — the column and the check.
- `apps/catalog/exceptions.py` — `CompareAtNotAbovePrice`, a `DomainError` with
  `code = "validation_error"`, status 400 and
  `details = {"compare_at_price": ["The compare-at price must be greater than the price."]}`,
  so it has the envelope of a serializer field error.
- `apps/catalog/services/products.py` — `compare_at_price` is in `VARIANT_FIELDS`.
  `create_variant` checks it whenever set; `update_variant` checks it only when
  `compare_at_price` is among the written fields, against the price after the same
  write (so `price_override` and `compare_at_price` can change together).
  `update_product` never checks: repricing past a compare-at ends the sale.
- `apps/catalog/selectors.py` — `_on_sale_variants()` is the SQL form of the
  predicate: `compare_at_price > COALESCE(price_override, <outer product>.base_price)`.
  `PRODUCT_ON_SALE = Exists(...)` of it serves both filters and the admin list.
  `_with_sale_variant()` annotates `sale_price` and `sale_compare_at_price` from a
  `Subquery` ordered by resolved price, `size__sort_order`, `pk`, limit 1; both the
  public list and detail selectors apply it.
- `apps/catalog/serializers.py` — product list and detail add `on_sale`
  (`sale_price is not None`), `sale_price`, `compare_at_price` (from
  `sale_compare_at_price`) and `discount_percent` (the model's helper). Public
  variants add `compare_at_price`, `on_sale` and `discount_percent` (the model
  properties).
- `apps/catalog/filters.py` — `OnSaleFilter`, a `TypedChoiceFilter` accepting only
  `true` and `false`, filtering or excluding on `PRODUCT_ON_SALE`. Used by
  `ProductFilter` and `AdminProductFilter`.
- `apps/backoffice/` — `AdminVariantSerializer` adds `compare_at_price`, `on_sale`
  and `discount_percent` (the same model properties as the storefront);
  `VariantWriteSerializer` accepts `compare_at_price` (nullable, ≥ 0.01);
  `list_products` annotates `on_sale=PRODUCT_ON_SALE` and the list item returns it;
  `?on_sale=` filters the admin list.
- `apps/catalog/workbook/` — the Variants sheet gains **Compare-at price (NPR)**
  (optional, price kind, decimal validation), a read-me rule, export of the value,
  and import through the variant services. Validation reports a compare-at not above
  the variant's price as `Sheet "Variants", row N, column "Compare-at price (NPR)":
  must be more than the price, 2450.00; leave it blank if the variant is not on
  sale`. The price is the row's override, else the base price on the Products sheet,
  else the database's.
- `apps/catalog/management/commands/_seed_catalogue.py` — `VariantSpec.compare_at_price`
  and an `on_sale(variants, *compare_at)` helper. Six variants are on sale: Anua
  Heartleaf Pore Control Cleansing Oil 200 ml, COSRX Snail 96 Mucin Essence 100 ml
  and SKIN1004 Centella Ampoule 55 ml at base price; Banila Co Clean It Zero 180 ml,
  Beauty of Joseon Glow Serum 60 ml and Anua Heartleaf 77% Toner 500 ml at an
  override. `seed_demo` writes the field.

---

## Remaining

- The Django admin (`/django-admin/`) does not show or edit `compare_at_price`. Its
  variant inline saves the model form directly, so exposing the field there would
  bypass the service's check. Superusers set sales through the admin app or the
  workbook.

---

## Decisions

### Decision: the check runs only when the compare-at is written

**Decision**

`update_variant` validates `compare_at_price` only when it is in the written fields.

**Reason**

The spec allows repricing past an existing compare-at. Checking on every write would
reject a `price_override` change that ends a sale.

### Decision: the rejection is a DomainError shaped like a field error

**Decision**

`CompareAtNotAbovePrice` uses the `validation_error` code, status 400, and puts the
message under `details.compare_at_price`.

**Reason**

The admin app shows serializer field errors from `details`. The rule needs the
resolved price, so it lives in the service, but it should look like any other
field error.

### Decision: the product's sale fields are subqueries

**Decision**

`sale_price` and `sale_compare_at_price` are two correlated `Subquery` annotations,
and `on_sale` and `discount_percent` are derived in the serializer.

**Reason**

It adds no query per product. The list keeps its three queries (count, page,
images), with or without `?on_sale=`.

---

## Gotchas

- An invalid `on_sale` value is
  `400 validation_error` with `details.on_sale` (django-filter's "Select a valid
  choice" message). `True`, `1` and `yes` are invalid. The older `in_stock` filter is
  a `BooleanFilter` and silently ignores bad values; `on_sale` does not.
- The SQL predicate in `_on_sale_variants` and the Python one in `discount_percent`
  must agree. Both treat a compare-at equal to the price as not on sale.
- The `resolved_price` annotation must stay an annotation inside the subquery.
  Ordering the subquery by the `Coalesce(..., OuterRef(...))` expression directly
  fails at runtime with "may only be used in a subquery".
- A workbook made from the template before this change has no Compare-at column.
  It still imports: a missing optional column means "not provided", so existing
  variants keep their compare-at, new variants get none, and the summary prints
  `column "Compare-at price (NPR)" not in workbook, left unchanged`. A present
  column with a blank cell does clear the compare-at and ends that sale.
- In the importer, an existing variant is given the product instance just written
  (`self.products`), because `Catalogue.variants` loaded its own copy of the product.
  Without that, a run that lowers a base price and starts a sale in the same run would
  check the compare-at against the old price and fail.
- `compare_at_price` is display-only. `price_cart`, the quote and order snapshots
  read `variant.price` and never the compare-at.

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
  `compare_at_price`:

  ```json
  { "error": { "code": "validation_error",
      "message": "The compare-at price must be greater than the price.",
      "details": { "compare_at_price": ["The compare-at price must be greater than the price."] } } }
  ```

  A value of 0 or less fails the serializer first (`min_value` 0.01), with the same
  code and field.
- Variant reads (in `products/{id}/` `variants[]` and in the variant create and
  update responses) also return `on_sale` and `discount_percent`, with the same
  rules as the public variant.
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

- `apps/catalog/tests/test_sale_prices.py` — the predicate against an override and a
  base price; no compare-at, one equal to the price, and one below it are not on
  sale; flooring (3200 → 2720 is 15, 999 → 850 is 14); the database refuses a zero
  compare-at; the services reject a compare-at at or below the price on create and on
  update (including against a new override in the same write); repricing the product
  or the override past the compare-at is allowed and ends the sale; clearing it;
  list and detail sale fields, and null fields when not on sale; the cheapest sale
  variant wins and a price tie goes to the smaller size; `?on_sale=true` and `false`,
  combined with brand and category, one row per product; `yes`, `1`, `True` and
  `maybe` are 400; the list stays at three queries.
- `apps/backoffice/tests/test_products.py` — `compare_at_price` round trip and clear,
  with `on_sale` and `discount_percent` on the variant response and in the product
  detail; creating a variant on sale; not above the price (equal, below, 0) is 400
  and writes nothing; repricing keeps the compare-at and ends the sale; the list's
  `on_sale` flag and filter, and 400 for a bad value.
- `apps/orders/tests/test_quote.py` — a variant on sale is quoted at its price.
- `apps/catalog/tests/test_catalogue_workbook.py` — the example catalogue carries a
  compare-at, so the export → import round trip covers it; import sets and clears
  it with a present blank cell; a workbook without the column keeps existing
  compare-at prices and creates new variants without one; a sale starts in the same
  run that lowers the base price; a compare-at not
  above the base price or the override is reported by sheet, row and column; one
  checked against a product only in the database.
- `apps/catalog/tests/test_seed_demo.py` — the seed data has six sale variants, a
  mix of override and base price, each above its price and published; the seeded
  variants are on sale.

---

## Files

```text
apps/catalog/models.py
apps/catalog/migrations/0003_compare_at_price.py
apps/catalog/exceptions.py
apps/catalog/services/products.py
apps/catalog/selectors.py
apps/catalog/serializers.py
apps/catalog/filters.py
apps/catalog/workbook/{layout,export,validation,importer}.py
apps/catalog/management/commands/{_seed_catalogue,seed_demo}.py
apps/backoffice/{serializers,selectors,filters}.py
apps/core/exceptions.py   # DomainError.status_code typed int
```
