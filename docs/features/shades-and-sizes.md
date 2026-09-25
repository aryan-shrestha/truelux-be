# Shades and sizes

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Make the variant axes fit cosmetics. A foundation varies by **shade**, a perfume by
**size** (volume), and a serum by neither. Colour, as clothing modelled it, becomes
shade with a swatch colour, and the shade axis becomes optional.

---

## Scope

What is included in this implementation?

- Rename `Color` → `Shade`, adding `hex_code`
- `ProductVariant.shade` becomes nullable
- `Size` is kept and holds volume or weight (`15 ml`, `50 ml`, `100 g`, `One size`)
- `?shade=` replaces `?color=` on the product list
- Public `GET /api/v1/shades/` and `GET /api/v1/sizes/` for the storefront's filters
- The order item snapshot `variant_color` becomes `variant_shade` (nullable)

What is explicitly outside the scope?

- Shade families or undertone grouping
- Shade matching or recommendation

---

## Context

[ADR 0010](../decisions/0010-shade-replaces-colour-and-is-optional.md) supersedes
[ADR 0007](0007-size-and-colour-are-lookup-tables.md) for the colour axis.
[ADR 0001](../decisions/0001-variant-is-the-stock-and-sku-unit.md) is unchanged: the
variant is still the stock and SKU unit.

---

## Planned

- `Shade(UUIDModel, TimeStampedModel)`: `name` (unique), `slug` (unique),
  `hex_code` (`CharField(max_length=7)`), `sort_order`. `db_table = "shade"`.
  `CheckConstraint shade_hex_code_format` using `hex_code__regex=r"^#[0-9A-Fa-f]{6}$"`.
- `ProductVariant.shade = ForeignKey(Shade, on_delete=PROTECT, null=True, blank=True)`.
- The unique constraint `product_variant_unique_product_size_shade` on
  `(product, size, shade)` with `nulls_distinct=False`, so a product cannot have
  two shadeless variants of the same size.
- Variant serializer: `"shade": {"name", "slug", "hex_code"} | null`.
- `OrderItem.variant_shade = CharField(max_length=50, blank=True)`, an empty string
  when the variant has no shade.
- Every `color` reference is renamed across models, serializers, filters, admin,
  seeds, emails and tests. Afterwards `grep -ri colou\?r apps/` returns only
  `hex_code`-related text.

---

## Implemented

- `apps/catalog/models.py` — `Shade` with the `shade_hex_code_format` check;
  `ProductVariant.shade` nullable `PROTECT`; `product_variant_unique_product_size_shade`
  with `nulls_distinct=False`. `Color` no longer exists.
- `apps/catalog/selectors.py` — `list_shades_in_use` / `list_sizes_in_use` keep a row
  only when an `Exists` subquery finds a variant of a published product of an active
  brand, so a value used twice is listed once.
- `apps/catalog/filters.py` — `?shade=<slug>` replaces `?color=` (a variant join with
  `.distinct()`, like `?size=`).
- `apps/catalog/serializers.py` — `ShadeSerializer` (`name`, `slug`, `hex_code`);
  variants render `shade` as that object or `null`.
- `apps/catalog/views.py`, `urls.py` — `ShadeListView` and `SizeListView` at
  `shades/` and `sizes/`: `AllowAny`, `catalog` scope, unpaginated.
- `apps/orders/models.py` — `OrderItem.variant_shade` (`blank=True`); `place_order`
  stores the shade name or `""`. Order serializers, the Django admin and the emails
  read it; the emails omit the shade when it is empty.
- `apps/catalog/admin.py` — `ShadeAdmin`; "Generate variants" takes optional shades
  and creates shadeless variants when none are ticked. SKUs omit the shade part then.
- Seed data: 14 sizes (grams, millilitres, `One size`) and 23 shades with hex codes.

---

## Remaining

None.

---

## Decisions

### Decision: `NULLS NOT DISTINCT` on the variant uniqueness constraint

**Decision**

Declared with Django's `UniqueConstraint(nulls_distinct=False)`.

**Reason**

ADR 0010. Without it PostgreSQL treats every `NULL` shade as distinct and a product
could hold any number of shadeless variants of one size.

**Consequence**

PostgreSQL 15+ is required. The local compose file runs 16; a Homebrew Postgres 14
on port 5432 would fail the migration.

---

## Gotchas

- `grep -ri colou\?r apps/` still matches the CSS `color:` properties in the email
  templates. Nothing in the domain is called colour any more.
- `/shades/` and `/sizes/` are facets, not the lookup tables: an unused shade, or one
  used only by hidden products, is not listed. The admin API lists every row.

---

## API

### `GET /api/v1/shades/` and `GET /api/v1/sizes/`

Public, `catalog` throttle scope, bare arrays in `sort_order` order. Only values used
by at least one variant of a visible product are returned.

```json
[{ "name": "Warm Beige", "slug": "warm-beige", "hex_code": "#D8A47F" }]
```

```json
[{ "name": "50 ml", "slug": "50-ml" }]
```

### Product detail variant

```json
{
  "id": "1b7d...",
  "size": { "name": "30 ml", "slug": "30-ml" },
  "shade": { "name": "Warm Beige", "slug": "warm-beige", "hex_code": "#D8A47F" },
  "price": "3200.00",
  "in_stock": true
}
```

`shade` is `null` for shadeless products. `?shade=<slug>` filters the list.

---

## Data changes

`shade` table with a hex-format check; `product_variant.shade_id` is nullable; the
unique constraint has `NULLS NOT DISTINCT`; `order_item.variant_shade` replaces
`variant_color`.

---

## Permissions

Reads are public. Writes go through `admin-api`.

---

## Tests

- `apps/catalog/tests/test_shades_and_sizes.py` — the hex check rejects `"red"`,
  `"#FFF"` and `"#GGGGGG"`; two shadeless variants of one product and size violate
  the constraint; `?shade=` excludes shadeless products; `shade` is an object or
  `null`; `/shades/` and `/sizes/` exclude unused and hidden-only values, in
  `sort_order`.
- `apps/orders/tests/test_checkout.py` — the snapshot stores the shade name, and
  `""` for a shadeless variant.
- `apps/catalog/tests/test_admin.py::test_generating_with_no_shade_creates_shadeless_variants`.

---

## Files

```text
apps/catalog/{models,selectors,filters,serializers,views,urls,admin}.py
apps/catalog/tests/test_shades_and_sizes.py
apps/orders/{models,services,serializers,admin}.py
apps/orders/templates/orders/email/
```
