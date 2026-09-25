# Product catalog

Status: Implemented

Last updated: 2026-09-22

---

## Goal

Model what the brand sells: categories, products, the size and colour variants that
carry stock and SKUs, and the photographs that sell them.

---

## Scope

What is included in this implementation?

- `Size`, `Color`, `Category`, `Product`, `ProductVariant`, and `ProductImage`
  models
- Per-variant SKU and stock quantity
- The stock decrement and restore services, with row locking
- Ordered product images with exactly one primary per product
- Publication state, so a product can be prepared before it is visible
- `SizeFactory`, `ColorFactory`, `CategoryFactory`, `ProductFactory`,
  `ProductVariantFactory`, `ProductImageFactory`

What is explicitly outside the scope?

- The public browsing endpoints, which belong to `catalog-browsing.md`
- The admin interface, which belongs to `merchant-admin.md`
- Any write API. Catalogue editing is admin-only in Phase 1
- Discounts, sale prices, and price history
- Product reviews, ratings, or related products
- A stock-movement ledger. Stock is a column, not a history
- The read selectors, which moved to `catalog-browsing.md` along with the query
  shapes and the query-count tests that make them correct

---

## Context

[ADR 0001](../decisions/0001-variant-is-the-stock-and-sku-unit.md) establishes the
central shape: `ProductVariant` is the sellable unit and carries `sku` and
`stock_quantity`. `Product` carries what does not vary. `OrderItem` will point at a
variant, never at a product.

[ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md) establishes
that stock is decremented at order placement, under `select_for_update()`, with
locks acquired in ascending `pk` order to avoid deadlock on multi-item carts.

[ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md) reverses this
document's original decision on size and colour: they are lookup tables, not
`CharField(choices=...)`, so the merchant can extend them without a deploy.

`apps/core/models.py` provides `UUIDModel` and `TimeStampedModel` as separate
abstract bases. The established inheritance order, set by `User`, is
`class X(UUIDModel, TimeStampedModel)`.

`media-storage.md` configures Cloudinary. `ProductImage.image` depends on it.

**This app owns a table that another app writes through.** `apps/orders`
decrements variant stock during checkout. That write goes through
`apps.catalog.services.decrement_variant_stock`, never through
`ProductVariant.objects` from inside an orders service — the lock belongs on the
side that owns the row.

---

## Planned

Delivered as described below. Retained for the record of intent:

- `Category`: name, unique slug, optional parent for one level of nesting, ordering
- `Product`: name, unique slug, description, `category` foreign key, `base_price`
  as `DecimalField`, `is_published`, ordering
- `ProductVariant`: `product` foreign key, `size`, `color`, unique `sku`,
  `stock_quantity`, optional `price_override`
- `ProductImage`: `product` foreign key, Cloudinary `image`, `alt_text`,
  `sort_order`, `is_primary`
- `apps/catalog/services.py`: `decrement_variant_stock`, `restore_variant_stock`
  (and, added later by `merchant-admin.md` (#10), `set_variant_stock`)
- `apps/catalog/exceptions.py`: `InsufficientStock`, `VariantUnavailable`
- Database constraints and indexes as listed under Data changes
- Factories and tests

---

## Implemented

- `Size` and `Color` lookup models — `name` (unique), `slug` (unique),
  `sort_order`, ordered by `sort_order` then `name`
- `Category`, with a nullable self-referential `parent` (`SET_NULL`)
- `Product`, with `base_price`, `is_published` defaulting to `False`, and an index
  on `(is_published, -created_at)`
- `ProductVariant`, with `size` and `color` as `PROTECT` foreign keys, a globally
  unique `sku`, `stock_quantity`, and a nullable `price_override`
- `ProductVariant.price`, the property that resolves `price_override` against
  `product.base_price`
- `ProductImage`, with a partial unique constraint giving exactly one primary per
  product and an index on `(product, sort_order)`
- All constraints and indexes listed under Data changes
- `apps/catalog/exceptions.py`: `VariantUnavailable` and `InsufficientStock`, the
  repository's first concrete `DomainError` subclasses
- `apps/catalog/services.py`: `decrement_variant_stock` and
  `restore_variant_stock`, both cart-level, both locking every row in one
  ascending-`pk` `select_for_update(of=("self",))`
- `apps/catalog/services.py`: `set_variant_stock`, added by `merchant-admin.md`
  (#10) so a merchant can record a counted total. Absolute, not a delta, and the
  only write to `stock_quantity` the admin can reach
- One migration, `apps/catalog/migrations/0001_initial.py`. No data migration
- Six factories and 25 tests, including the concurrency test

---

## Remaining

- ~~Nothing populates `size` or `color`.~~ `SizeAdmin` and `ColorAdmin` landed with
  `merchant-admin.md` (#10), so a merchant fills both tables themselves. `demo-seed`
  (#11) fills them for development. Both tables still ship **empty**, which remains
  true of any fresh database. See
  [ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md).
- **`Category.parent` depth is still unenforced**, and both features that were
  supposed to enforce it have landed without doing so. The serializer renders one
  level (#5) and `CategoryAdmin` offers a parent field with no depth check (#10), so
  a merchant can still build a three-level tree that the category endpoint will not
  render. Nothing in the database stops it either.
- `Product.base_price` has no `CheckConstraint`. Data changes below never specified
  one and the field is admin-only in Phase 1, so none was added — but a negative
  list price is currently storable.

---

## Decisions

### Decision: size and colour are lookup tables (supersedes the choices decision)

**Decision**

`Size` and `Color` are models. `ProductVariant.size` and `ProductVariant.color`
are non-nullable `PROTECT` foreign keys to them. `apps/catalog/constants.py` does
not exist.

Recorded in full as
[ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md).

**Reason**

The superseded decision below required a code change and a deploy to add a colour.
The brand changes colourways per drop, which put engineering in the path of a
merchandising choice several times a season. A foreign key constrains the value at
least as strictly as `choices` does — more strictly, in fact, since the database
enforces it on every writer rather than only on model validation.

**Consequence**

Adding a size or colour is data entry. A size already used by a variant cannot be
deleted (`PROTECT`), and there is no `is_active` flag to hide one, so a
discontinued size stays in the picker. Both tables ship empty; #10 is what
populates them.

#### Superseded: size and colour are constrained choices, not free text

> **Decision**
>
> `size` and `color` are `CharField` with `choices`, defined as module constants in
> `apps/catalog/constants.py`.
>
> **Reason**
>
> Free text produces "M", "m", "Medium", and "medum" in the same table, which makes
> filtering unreliable and the variant uniqueness constraint meaningless.
>
> **Consequence**
>
> Adding a size requires a code change and a deploy, not an admin edit. For a brand
> with a fixed size run this is correct; a brand that invents sizes per drop would
> need a lookup table instead.

Superseded because the brand is the second case, which this decision's own
Consequence anticipated. The concern that motivated it — inconsistent spellings in
one column — is satisfied more strongly by a foreign key.

### Decision: price lives on the product, with an optional per-variant override

**Decision**

`Product.base_price` is authoritative. `ProductVariant.price_override` is nullable
and used only where a variant genuinely costs more.

**Reason**

Almost every garment is one price across sizes. Requiring a price on all fifteen
variants of a shirt means fifteen chances to mistype one. The override covers the
real exception, which is an extended size costing more.

**Consequence**

Every price read must resolve the override, so it belongs in one place — the
`ProductVariant.price` property, returning a `Decimal` — rather than being
recomputed at each call site. `checkout.md` snapshots the resolved value onto
the order line. There is no `Money` type in this repository; amounts are
`Decimal` and the currency is implicit.

### Decision: `InsufficientStock` does not report the remaining quantity

**Decision**

`InsufficientStock.details` carries `variant_id` and `requested`, both of which are
the client's own input echoed back. It does **not** carry the available count.

**Reason**

`catalog-browsing.md` withholds `stock_quantity` from every serializer because
exact inventory levels are commercially sensitive and competitors read public APIs.
Checkout is `AllowAny` under [ADR 0003](../decisions/0003-guest-checkout-with-opaque-order-access-tokens.md),
so returning the count in an error would hand back through the checkout endpoint
precisely what the browsing endpoint refuses to publish — and more cheaply, since
one POST per variant with an absurd quantity enumerates the whole catalogue in a
single pass rather than by binary search.

**Consequence**

The storefront cannot say "only 2 left" from the error alone. It knows which line
failed, and re-reads the product for the boolean `in_stock`. Do not add the count
back as a UX improvement without revisiting the browsing rule at the same time;
the two must agree.

### Decision: one primary image per product, enforced by a partial unique constraint

**Decision**

A `UniqueConstraint` on `(product, is_primary)` with
`condition=Q(is_primary=True)`.

**Reason**

The product card needs exactly one image. Enforcing it in the serializer or the
admin leaves the database able to hold two, and something eventually will.

**Consequence**

Setting a new primary requires clearing the old one in the same transaction.
Naively saving a second primary raises `IntegrityError`, which the handler turns
into a 409.

---

## Gotchas

- **`OrderItem.variant` is `PROTECT`, not `CASCADE`.** Deleting a variant that has
  been ordered would destroy order history. The merchant unpublishes instead of
  deleting, and the admin should make that the obvious path.
- **Locks are acquired in ascending `pk` order.** A cart with two variants locked
  in opposite orders by two concurrent checkouts deadlocks, and Postgres resolves
  it by killing one transaction. This is the single most important line in
  `decrement_variant_stock`, and it is why both stock services take the whole
  cart rather than one variant: a caller looping over single-variant calls would
  own the ordering rule, and would eventually get it wrong.
- **`select_for_update(of=("self",))`, not a bare `select_for_update()`.** The
  lock query joins `product` to read `is_published` and `base_price`. Without
  `of`, PostgreSQL locks the joined product rows too — rows the operation never
  writes, and a second deadlock surface between checkouts of different variants
  of the same product.
- A `CheckConstraint` keeps `stock_quantity >= 0`, so a service bug surfaces as a
  409 rather than as silently negative inventory.
- The variant uniqueness constraint is on `(product, size, color)`, not on `sku`
  alone. `sku` is *also* unique, globally — the two constraints answer different
  questions.
- A product list showing "in stock" reaches through variants. `catalog-browsing.md`
  answers it with an `Exists` annotation rather than a prefetch, so no variant row
  crosses the network for a boolean; that document owns the query shape, this one
  owns the relations that make it possible.
- Cloudinary upload happens **before** any transaction opens. See
  `media-storage.md`.
- `Category.parent` allows one level. Nothing enforces the depth limit in the
  database; the admin and the serializer must, or a merchant will build a tree.
- **`ProductVariant` has no `Meta.ordering`.** Ordering by `size__sort_order`
  would join two tables on every variant read, including every prefetch.
  `catalog-browsing.md` orders explicitly where it renders variants.
- `ProductVariant.price` reads `self.product.base_price` when `price_override`
  is null, which is a query per variant unless `product` is already selected.
  The stock services `select_related("product")` for exactly this reason.
- **A non-positive quantity raises `ValueError`, not a `DomainError`.** Zero or
  negative would sail past the availability check and *add* stock on the
  decrement path. It means a broken caller, not a rejected customer, so it gets
  no public error code — which makes it the serializer's job to stop it.
  `CheckoutSerializer` must declare `quantity` as `IntegerField(min_value=1)`,
  or a client sending `0` receives a 500 rather than a 400.
- **`stock_quantity` is an `IntegerField`, not a `PositiveIntegerField`.**
  The positive variant emits its own unnamed `CHECK (>= 0)`, which would sit
  alongside `product_variant_stock_not_negative` as a second identical
  constraint on the same column. Changing it back reintroduces that duplicate.
- **`size` and `color` are non-nullable on purpose.** PostgreSQL treats NULLs as
  distinct, so a nullable colour would silently defeat the
  `(product, size, color)` unique constraint. A garment with no colour axis
  needs a real "One colour" row to point at.

---

## API

None. This feature defines models and services only. The read endpoints are in
`catalog-browsing.md`; there is no write API in Phase 1.

---

## Data changes

**`size`** — UUID pk, timestamps, `name` (unique), `slug` (unique),
`sort_order`.

**`color`** — UUID pk, timestamps, `name` (unique), `slug` (unique),
`sort_order`.

**`category`** — UUID pk, timestamps, `name`, `slug` (unique), `parent`
(self-FK, `SET_NULL`, nullable), `sort_order`.
Index on `slug`.

**`product`** — UUID pk, timestamps, `name`, `slug` (unique), `description`,
`category` (FK, `PROTECT`), `base_price` (`DecimalField`), `is_published`,
`sort_order`.
Indexes on `slug`, and on `(is_published, -created_at)` for the default list query.

**`product_variant`** — UUID pk, timestamps, `product` (FK, `CASCADE`), `size`
(FK to `size`, `PROTECT`), `color` (FK to `color`, `PROTECT`), `sku` (unique),
`stock_quantity`, `price_override` (nullable).
Constraints: unique `(product, size, color)`; check `stock_quantity >= 0`; check
`price_override` is null or positive.
Index on `product`.

**`product_image`** — UUID pk, timestamps, `product` (FK, `CASCADE`), `image`
(Cloudinary), `alt_text`, `sort_order`, `is_primary`.
Constraint: unique `(product, is_primary)` where `is_primary` is true.
Index on `(product, sort_order)`.

`CASCADE` is used only where the child is meaningless without the parent — a
variant or an image without its product. Every other relation is `PROTECT` or
`SET_NULL`.

The indexes this section asks for on `category.slug`, `product.slug` and
`product_variant.product` are not declared a second time in `Meta.indexes`:
`unique=True` and `ForeignKey` already create them, and a duplicate declaration
would mean two identical indexes on the same column.

One migration. No data migration.

---

## Permissions

No API permissions, because there is no API in this feature.

Write access is admin-only, requiring `is_staff`. Per `convention.md`, Django model
permissions and groups are used by the admin and never by the API.

One thing to state plainly: **an unpublished product is not private.** Its
Cloudinary image URLs are public and permanent regardless of `is_published`. The
flag controls API visibility, not asset visibility.

---

## Tests

`apps/catalog/tests/test_models.py`

- `test_duplicate_size_and_color_for_product_violates_constraint`
- `test_same_size_and_color_on_another_product_is_allowed`
- `test_duplicate_sku_violates_constraint`
- `test_negative_stock_violates_constraint`
- `test_zero_price_override_violates_constraint`
- `test_second_primary_image_violates_constraint`
- `test_many_non_primary_images_are_allowed_for_one_product`
- `test_variant_price_falls_back_to_product_base_price`
- `test_variant_price_override_wins_over_base_price`
- `test_deleting_a_size_in_use_is_protected`
- `test_deleting_an_unused_color_is_allowed`
- `test_deleting_a_product_cascades_to_variants_and_images`
- `test_product_image_persists_a_storage_reference` — the `ImageField` coverage
  `media-storage.md` deferred to this feature

`apps/catalog/tests/test_services.py`

- `test_decrement_variant_stock_reduces_quantity`
- `test_decrement_returns_locked_variants_for_price_resolution`
- `test_decrement_beyond_available_raises_insufficient_stock`
- `test_decrement_is_all_or_nothing_across_the_cart`
- `test_decrement_unknown_variant_raises_variant_unavailable`
- `test_decrement_unpublished_variant_raises_variant_unavailable`
- `test_restore_variant_stock_returns_quantity`
- `test_restore_variant_stock_ignores_publication_state`
- `test_non_positive_quantity_is_rejected_before_any_write` — parametrised
  over `0` and `-3`
- `test_restore_also_rejects_a_non_positive_quantity`
- `test_concurrent_decrement_does_not_oversell` — two threads racing for the last
  unit. Verified meaningful: with `select_for_update()` removed it fails, because
  both buyers succeed

---

## Files

```text
apps/catalog/
├── __init__.py
├── apps.py
├── models.py
├── services.py
├── exceptions.py
├── migrations/
│   └── 0001_initial.py
└── tests/
    ├── factories.py
    ├── test_models.py
    └── test_services.py
config/settings/base.py          apps.catalog in INSTALLED_APPS
```

`constants.py` is absent by decision, not by oversight: ADR 0007 made the choice
sets into rows. `apps/catalog/selectors.py` now exists but belongs to
`catalog-browsing.md` (#5), which owns its prefetch shape and its query-count
tests.

---

## Future context

The cartesian-product problem is real and lands in `merchant-admin.md`: a garment
in five sizes and three colours is fifteen rows, and no merchant will type fifteen
rows. The admin must generate them from a selected set of sizes and colours. Read
that document before building `apps/catalog/admin.py`.

`price_override` is nullable on purpose. Code that reads a variant's price must go
through `ProductVariant.price`; a direct read of `price_override` will be `None`
for almost every row and silently produce a zero or a crash.

`decrement_variant_stock` and `restore_variant_stock` take the whole cart as a
`Mapping[UUID, int]` and return the locked variants keyed by id. The return value
is not incidental: it is what lets `place_order` read each unit price without
refetching rows it already holds a lock on. A caller that refetches is opening a
window between the lock and the price it snapshots.

When Phase 2 adds discounts, they belong on a separate model keyed to product or
category, not as a mutable column here. `base_price` is the list price and should
stay the list price, or order history stops making sense.
