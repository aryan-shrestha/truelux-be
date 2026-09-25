# Shades and sizes

Status: Planned

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

To be written:

- The hex check rejects `"red"`, `"#FFF"` and `"#GGGGGG"`.
- Two shadeless variants of the same product and size violate the unique
  constraint.
- `?shade=` filters; shadeless products are excluded by a shade filter.
- `/shades/` and `/sizes/` exclude values used only by hidden products.
- Checkout snapshots `variant_shade` and stores `""` for a shadeless variant.
