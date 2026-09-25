# ADR 0001: The variant is the stock and SKU unit

Status: Accepted

Date: 2026-09-20

Supersedes: None

Amended by [ADR 0007](0007-size-and-colour-are-lookup-tables.md): the two axes
are stored as `Size` and `Color` lookup tables with foreign keys from
`ProductVariant`, not as `CharField(choices=...)`. This ADR's rejection of a
generic attribute model still stands; its assumption that both axes are "known
in advance" does not.

---

## Context

The store sells apparel. A single garment exists in several sizes and often
several colours, and those combinations do not sell at the same rate — mediums
sell out while extra-larges sit. The catalogue has to answer two questions that a
product-level model cannot: *is this shirt available in M?* and *what exactly did
this customer buy?*

The decision is where `sku` and `stock_quantity` live. Putting them on `Product`
keeps the schema small and the admin trivial. Putting them on a separate
`ProductVariant` row per size × colour combination makes every downstream feature
— browsing, checkout, order items, the admin — more expensive.

This has to be decided before any model is written, because every Phase 1 feature
document assumes one answer or the other.

## Decision

`ProductVariant` is the sellable unit. It carries `size`, `color`, `sku`
(unique), and `stock_quantity`. `Product` carries the things that do not vary:
name, slug, description, category, base price, and images.

`OrderItem` holds a foreign key to `ProductVariant`, not to `Product`.

Stock is an integer column on the variant. There is no separate inventory table
and no stock-movement ledger.

## Reason

Per-size stock is not an optimisation; it is the product requirement. A store that
cannot tell a customer which sizes are left will sell garments it does not have,
and the failure surfaces as a refund and an apology rather than as a validation
error.

A variant is also the only honest target for an order line. If `OrderItem` pointed
at `Product` with a free-text `size` string, nothing would constrain that string
to a size the product actually comes in, and the merchant would be reconciling
typos against a packing list.

The SKU belongs on the same row for the same reason: a SKU identifies a physical
thing in a box, and the physical thing is a medium black shirt, not "shirt".

## Alternatives considered

### Product-level stock with size as a free-text option

Why it was not chosen: it cannot answer "available in M", it cannot prevent
overselling one size while another is in stock, and it pushes validation of the
size value into every caller. It is genuinely simpler and genuinely wrong for
apparel. It would be the right choice for a catalogue of one-size items.

### A JSON attribute bag on `Product`

Why it was not chosen: stock inside a JSON column cannot be decremented under a
row lock, cannot carry a unique constraint on SKU, and cannot be a foreign-key
target for `OrderItem`. Concurrency correctness is the whole problem here, and
JSON gives it up.

### A generic attribute/option/value model (EAV)

Why it was not chosen: it buys arbitrary attribute types the brand does not need,
at the cost of three extra tables and a query for every product card. Phase 1 has
exactly two axes, size and colour, both known in advance.

## Consequences

### Positive

- Stock is accurate per size, and overselling is preventable with a row lock.
- `OrderItem.variant_id` identifies precisely what was bought, forever.
- SKU uniqueness is a database constraint rather than a merchant convention.
- Adding a third axis later means adding a column, not redesigning the order line.

### Negative

- Row count is combinatorial. A garment in five sizes and three colours is fifteen
  rows, and the merchant will not type fifteen rows by hand — the admin has to
  generate the cartesian product for them.
- A product list endpoint that shows an "in stock" badge must reach through
  variants, so the list query needs `prefetch_related` two levels deep. A missing
  prefetch here is an N+1 that is invisible locally and expensive across the
  network to Supabase.
- "Show me everything available in M" is a subquery over a related table, not a
  column filter.

### Constraints introduced

- `ProductVariant.sku` is unique across the whole table, not per product.
- A variant may not be deleted once an `OrderItem` references it. The foreign key
  is `PROTECT`, so order history cannot be destroyed by a catalogue edit.
- Every stock write goes through `apps.catalog.services` under
  `select_for_update()`. Nothing outside `apps/catalog` touches
  `ProductVariant.objects` for a write.

## Implementation

```text
apps/catalog/models.py       Product, ProductVariant, ProductImage, Category, Size, Color
apps/catalog/services.py     decrement_variant_stock, restore_variant_stock
apps/catalog/admin.py        variant generation from selected sizes and colours
apps/orders/models.py        OrderItem.variant -> ProductVariant (PROTECT)
docs/features/product-catalog.md
```

## Future reconsideration

Revisit if the brand starts selling made-to-order or unsized items in volume, where
a variant row per garment is pure overhead. Also revisit if a third and fourth
axis appear (fabric, fit), at which point the cartesian product becomes large
enough that a generic option model is cheaper than the combinatorics.

A stock-movement ledger becomes worth adding when the merchant needs to answer
*why* stock changed, not just what it is. Phase 1 does not.
