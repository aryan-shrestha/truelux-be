# ADR 0009: Brand is a first-class model

Status: Accepted

Date: 2026-09-25

Supersedes: None

---

## Context

TrueLux sells many brands. Customers browse and filter by brand, the merchant
adds brands without a deploy, and a brand has its own logo and description. The
question is whether brand is a text attribute on `Product` or a model of its own.

---

## Decision

`Brand` is a model in `apps/catalog` and `Product.brand` is a required foreign key
with `on_delete=PROTECT`. `Brand.is_active` hides a brand and all its products from
the public API without deleting anything.

---

## Reason

A foreign key keeps `Lumiere`, `Lumière` and `lumiere` from coexisting, which a
text column cannot. It is the same reasoning [ADR 0007](0007-size-and-colour-are-lookup-tables.md)
applied to sizes. A brand also carries data of its own (a logo and a description),
and the brand filter needs a stable slug.

---

## Alternatives considered

### A `brand` CharField on Product

Why it was not chosen: no place for a logo or description, typos split the filter,
and renaming a brand would mean rewriting every product.

---

## Consequences

### Positive

- The brand filter, brand pages and admin management all read one table.

### Negative

- Every product write needs a brand, so the seed and the tests must create one.

### Constraints introduced

- Public selectors must filter `brand__is_active=True` alongside `is_published=True`.

---

## Implementation

```text
apps/catalog/models.py
apps/catalog/selectors.py
docs/features/brands.md
```
