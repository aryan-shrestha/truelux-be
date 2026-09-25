# ADR 0010: Shade replaces colour, and shade is optional

Status: Accepted

Date: 2026-09-25

Supersedes: The colour axis of [ADR 0007](0007-size-and-colour-are-lookup-tables.md)

---

## Context

Clothing varied every garment by size and colour. Cosmetics vary a foundation by
shade, a perfume by volume, and a cleanser by neither. A required colour axis would
force a fake "None" colour onto most of the catalogue, and a colour name alone
cannot draw a swatch.

---

## Decision

`Color` becomes `Shade` with a `hex_code` (`#RRGGBB`, enforced by a check
constraint). `ProductVariant.shade` is nullable. The `(product, size, shade)`
uniqueness constraint uses `NULLS NOT DISTINCT`. `Size` is kept, and holds volume or
weight, with `One size` for products that have a single presentation.

---

## Reason

A null shade states the truth ("this product has no shades") instead of a
sentinel row the storefront would have to know to hide. `NULLS NOT DISTINCT`
(PostgreSQL 15+, which Supabase runs) keeps the uniqueness guarantee that a null
would otherwise break. The hex code is what the storefront and the admin draw.

---

## Alternatives considered

### A sentinel "No shade" row

Why it was not chosen: every client would have to special-case one slug, and the
filter would offer a meaningless option.

---

## Consequences

### Positive

- Swatches render from data. Shadeless products need no workaround.

### Negative

- Clients must handle `shade: null`.

### Constraints introduced

- Requires PostgreSQL 15 or later for `NULLS NOT DISTINCT`.

---

## Implementation

```text
apps/catalog/models.py
docs/features/shades-and-sizes.md
```
