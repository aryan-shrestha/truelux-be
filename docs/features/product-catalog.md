# Product catalog

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Model what TrueLux sells: brands, categories, products, the size and shade variants
that carry stock and SKUs, and the images that sell them.

---

## Scope

What is included in this implementation?

- `Brand`, `Category`, `Size`, `Shade`, `Product`, `ProductVariant`, `ProductImage`
- Per-variant SKU, stock quantity and optional price override
- The stock services (decrement, restore, set), with row locking
- The catalogue write services used by the admin API and the Django admin
- Ordered product images with at most one primary per product
- Publication state, and brand activation, controlling public visibility

What is explicitly outside the scope?

- The public read endpoints (`catalog-browsing.md`), the staff API (`admin-api.md`)
- Discounts, price history, reviews, a stock-movement ledger

---

## Context

[ADR 0001](../decisions/0001-variant-is-the-stock-and-sku-unit.md): the variant is
the sellable, stock-carrying unit. [ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md):
stock is decremented at placement under ascending-`pk` row locks.
[ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md): sizes are a
lookup table. [ADR 0009](../decisions/0009-brand-is-a-first-class-model.md): brand is
a model. [ADR 0010](../decisions/0010-shade-replaces-colour-and-is-optional.md): the
colour axis became an optional shade. `apps/orders` writes stock only through
`apps.catalog.services`.

---

## Implemented

- `apps/catalog/models.py` — all seven models (see Data changes);
  `ProductVariant.price` resolves `price_override` against `product.base_price`.
- `apps/catalog/exceptions.py` — `VariantUnavailable`, `InsufficientStock`,
  `ProductHasNoVariants`.
- `apps/catalog/services/stock.py` — `decrement_variant_stock`,
  `restore_variant_stock` (whole-cart, one ascending-`pk`
  `select_for_update(of=("self",))`) and `set_variant_stock` (absolute count, locked).
- `apps/catalog/services/products.py` — create/update/delete for products, variants
  and images; `set_product_published` and `update_product` refuse to publish a
  product without variants; `add_product_image` uploads before its transaction;
  promoting a primary clears the old one in the same transaction.
- `apps/catalog/services/taxonomy.py` — create/update/delete for brands, categories,
  shades and sizes, with slug derivation and a category-cycle check.
- `apps/catalog/services/__init__.py` re-exports every public service.
- One fresh migration, `apps/catalog/migrations/0001_initial.py`.

---

## Remaining

None.

---

## Decisions

### Decision: omitted slugs are derived and made unique

**Decision**

`unique_slug` slugifies the name (so `Lumière` becomes `lumiere`) and appends `-2`,
`-3`… until no row has it.

**Reason**

The admin API makes `slug` optional. A concurrent writer can still collide; the
unique constraint then answers `409 conflict`.

### Decision: write services take model instances for relations

**Decision**

Services receive `brand`, `category`, `size`, `shade` and `parent` as instances,
resolved and validated by the serializers.

**Reason**

An unknown id is a 400 naming the field rather than a database error.

---

## Gotchas

- `stock_quantity` and `OrderItem.quantity` are `IntegerField`s so only the named
  check constraints apply.
- `decrement_variant_stock` joins `product__brand`, `size` and `shade` because
  checkout reads them while holding the locks.
- `set_variant_stock`'s lock exists so the logged `previous` value is accurate; the
  write is absolute.
- Deleting anything referenced (`PROTECT`) raises `ProtectedError`, a 409.
- Deleting an image deletes the row only; the Cloudinary asset remains.

---

## Data changes

- `brand`: `name` (unique), `slug` (unique), `description`, `logo`, `is_active`,
  `sort_order`.
- `category`: `name`, `slug` (unique), `parent` (self, `SET_NULL`), `sort_order`.
- `size`: `name` (unique), `slug` (unique), `sort_order`.
- `shade`: `name` (unique), `slug` (unique), `hex_code` (check
  `shade_hex_code_format`), `sort_order`.
- `product`: `name`, `slug` (unique), `description`, `brand` (`PROTECT`),
  `category` (`PROTECT`), `base_price`, `is_published`, `sort_order`; index
  `product_published_crtd_idx`.
- `product_variant`: `product` (`CASCADE`), `size` (`PROTECT`), `shade`
  (`PROTECT`, nullable), `sku` (unique), `stock_quantity`, `price_override`;
  `product_variant_unique_product_size_shade` (`NULLS NOT DISTINCT`),
  `product_variant_stock_not_negative`, `product_variant_price_override_positive`.
- `product_image`: `product` (`CASCADE`), `image`, `alt_text`, `sort_order`,
  `is_primary`; partial unique `product_image_one_primary_per_product`; index
  `product_image_sort_idx`.

---

## Permissions

No API of its own; see `catalog-browsing.md` and `admin-api.md`.

---

## Tests

- `apps/catalog/tests/test_models.py` — constraints, `PROTECT`, cascades, price.
- `apps/catalog/tests/test_services.py` — decrement, restore and set, including the
  concurrency tests.
- `apps/catalog/tests/test_shades_and_sizes.py`, `test_brands.py` — the new models.
- `apps/backoffice/tests/test_products.py`, `test_taxonomy.py` — the write services
  through the admin API.

---

## Files

```text
apps/catalog/
├── admin.py
├── exceptions.py
├── models.py
├── services/{__init__,_slugs,products,stock,taxonomy}.py
└── tests/
```
