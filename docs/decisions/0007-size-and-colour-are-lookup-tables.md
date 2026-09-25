# ADR 0007: Size and colour are lookup tables

Status: Accepted; the colour axis is superseded by [ADR 0010](0010-shade-replaces-colour-and-is-optional.md)

Date: 2026-09-20

Supersedes: the "size and colour are constrained choices, not free text" decision
in `docs/features/product-catalog.md`

---

## Context

[ADR 0001](0001-variant-is-the-stock-and-sku-unit.md) fixed the variant as the
sellable unit and named its two axes, size and colour. It did not decide how those
axes are *stored*, and `product-catalog.md` answered that with
`CharField(choices=...)` fed by module constants in `apps/catalog/constants.py`.

That answer carried an explicit cost, stated in its own Consequence: *"Adding a
size requires a code change and a deploy, not an admin edit. For a brand with a
fixed size run this is correct; a brand that invents sizes per drop would need a
lookup table instead."*

The brand is the second case. Colours in particular change every drop, and a
colour is not a schema decision — it is merchandising data. Requiring an engineer,
a pull request and a Render deploy to sell a garment in sand instead of beige puts
a deploy in the critical path of a merchandising choice.

The question is therefore where the set of valid sizes and colours lives: in
Python, or in the database.

## Decision

`Size` and `Color` are models. Each carries `name` (unique), `slug` (unique) and
`sort_order`, on the repository's standard `UUIDModel, TimeStampedModel` bases.

`ProductVariant.size` and `ProductVariant.color` are non-nullable foreign keys to
them, both `on_delete=PROTECT`.

`apps/catalog/constants.py` is not created. The uniqueness constraint on
`(product, size, color)` is unchanged and still meaningful, because it now spans
two foreign keys rather than two free-text columns.

There is no `is_active` retirement flag. Removal means deleting the row, which
`PROTECT` permits only when nothing references it.

## Reason

The original decision's stated purpose was to stop `"M"`, `"m"`, `"Medium"` and
`"medum"` from coexisting in one column. A lookup table achieves that at least as
well as `choices` does — better, in fact, because a foreign key is enforced by the
database on every write, including writes that bypass Django's validation, while
`choices` is enforced only by model validation and is invisible to the database.

What the lookup table adds is that the set is data. The merchant extends it
without a deploy, and `sort_order` lets S, M, L render in body order rather than
alphabetical order, which `choices` gave implicitly through declaration order and
which a naive query over a `CharField` loses.

`PROTECT` rather than `SET_NULL` or `CASCADE` because a variant without a size is
not a meaningful row, and because `ProductVariant` is the target of
`OrderItem.variant` under ADR 0001 — a delete that cascaded through a size into
order history would destroy the record of what a customer bought.

## Alternatives considered

### `CharField(choices=...)` with module constants

The superseded decision. Why it was not chosen: adding a colour becomes a code
change, a review and a deploy. For a brand whose colourway changes per drop this
puts engineering in the path of a merchandising decision several times a season,
and the failure mode is a merchant who cannot list a product they are holding in
stock.

### One `VariantOption` table with a `kind` column

A single table holding both axes, discriminated by `kind="size"|"color"`.

Why it was not chosen: both foreign keys would point at the same table, so nothing
in the database would stop a colour being stored in a variant's size slot. That
check would move into application code, which is the opposite of the reason for
making this a table at all. It also drifts toward the EAV shape ADR 0001 rejected,
while saving exactly one table.

### A lookup table plus an `is_active` retirement flag

Why it was not chosen: it adds a column and a filtering obligation that every
future selector and admin form must remember, to solve a problem the brand does
not yet have. `PROTECT` already prevents destroying history, and a discontinued
size with no variants can simply be deleted. Revisit if retired sizes accumulate
in the pickers.

## Consequences

### Positive

- Adding or removing a size or colour is data entry, not a deploy.
- The valid set is enforced by a foreign key, so it holds against every writer,
  including the admin, a data migration and a psql session.
- `sort_order` makes size ordering explicit and correct.
- The `(product, size, color)` uniqueness constraint is strengthened, because the
  compared values are now identifiers rather than strings that can differ by case
  or whitespace.

### Negative

- Two more tables, and two more joins on any query that renders a variant's size
  or colour. `catalog-browsing.md`'s query-count tests become more valuable, not
  less.
- **Nothing populates the tables yet.** An empty `size` table means no variant can
  be created at all, and the admin that would let staff add rows lands with
  `merchant-admin.md` (#10). Until then the only ways in are the Django shell and
  a data migration.
- A size that is in use cannot be deleted; the merchant gets a `ProtectedError` in
  the admin. With no `is_active` flag there is no way to hide it from the picker
  short of deleting every variant that uses it.

### Constraints introduced

- `ProductVariant.size` and `.color` are `PROTECT`. A future service must not
  force-delete through them.
- Both are non-nullable. This is what keeps the `(product, size, color)` unique
  constraint honest: PostgreSQL treats NULLs as distinct, so a nullable colour
  would silently permit duplicate variants.
- A garment with no colour axis needs a real row to point at — a "One colour"
  `Color` — rather than a NULL.

## Implementation

```text
apps/catalog/models.py                          Size, Color, ProductVariant
apps/catalog/migrations/0001_initial.py
apps/catalog/tests/factories.py                 SizeFactory, ColorFactory
apps/catalog/tests/test_models.py               PROTECT and uniqueness coverage
docs/features/product-catalog.md                supersedes the old decision
docs/features/merchant-admin.md                 SizeAdmin, ColorAdmin
docs/decisions/0001-variant-is-the-stock-and-sku-unit.md
```

## Future reconsideration

Revisit if a third and fourth axis appear (fabric, fit). Two lookup tables is the
right shape for two axes; four suggests the generic option model ADR 0001 rejected,
and the combinatorics would by then justify it.

Revisit the absence of `is_active` when the first size is discontinued while
variants still reference it, which is the point at which the merchant needs to hide
a row they cannot delete.
