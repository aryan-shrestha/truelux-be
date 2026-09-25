# Brands

Status: Planned

Last updated: 2026-09-25

---

## Goal

TrueLux is a multi-brand cosmetics retailer. Customers shop by brand as often as by
category, so a product must belong to a brand the merchant manages as data, and the
catalogue must be filterable by it.

---

## Scope

What is included in this implementation?

- `Brand` model in `apps/catalog`, managed through the admin API (`admin-api.md`)
  and the Django admin
- `Product.brand`, a required foreign key
- `brand` object on every product list and detail item
- `?brand=` filter on the product list, repeatable for several brands
- Public `GET /api/v1/brands/` and `GET /api/v1/brands/{slug}/`
- Seeded brands in `seed_demo`

What is explicitly outside the scope?

- Brand landing-page content beyond `description` and `logo`
- Brand-level discounts or ordering rules
- A brand's own category tree

---

## Context

[ADR 0009](../decisions/0009-brand-is-a-first-class-model.md) records why brand is a
model rather than a product attribute. The filter follows the existing
`apps/catalog/filters.py` conventions; the list and detail serializers are in
`apps/catalog/serializers.py`; reads belong in `apps/catalog/selectors.py`.

---

## Planned

- `Brand(UUIDModel, TimeStampedModel)`: `name` (unique, max 150), `slug` (unique),
  `description` (blank allowed), `logo` (`ImageField`, optional, `upload_to="brands/"`),
  `is_active` (default `True`), `sort_order`. Ordering `["sort_order", "name"]`.
  `db_table = "brand"`.
- `Product.brand = ForeignKey(Brand, on_delete=PROTECT, related_name="products")`.
  A brand with products cannot be deleted; the merchant deactivates it instead.
- An inactive brand hides its products from every public endpoint, exactly as an
  unpublished product is hidden. Public selectors filter
  `is_published=True, brand__is_active=True`.
- `select_related("brand")` in the list and detail selectors: no N+1.
- `ProductFilter.brand`: a multiple-choice filter on `brand__slug`
  (`?brand=lumiere&brand=verde` matches either).
- Brand endpoints use the `catalog` throttle scope and are unpaginated bare arrays,
  like `/categories/`.

---

## API

### `GET /api/v1/brands/`

Public. Active brands only, in `sort_order, name` order.

```json
[
  {
    "name": "Lumière",
    "slug": "lumiere",
    "description": "French-inspired complexion care.",
    "logo_url": "https://res.cloudinary.com/.../brands/lumiere.png",
    "product_count": 6
  }
]
```

`logo_url` is `null` when no logo is uploaded. `product_count` counts published
products only.

### `GET /api/v1/brands/{slug}/`

Public. Same object as a list item. An unknown **or inactive** slug returns the
same 404 `not_found`.

### Product list and detail

Every product item gains:

```json
"brand": { "name": "Lumière", "slug": "lumiere" }
```

`GET /api/v1/products/?brand=<slug>` is repeatable.

---

## Data changes

- New table `brand`, unique `name`, unique `slug`.
- `product.brand_id` not null, `PROTECT`, indexed by the FK.
- The migrations are regenerated from scratch for TrueLux, so no data migration
  is needed.

---

## Permissions

Reads are public (`AllowAny`). Writes go through `admin-api` only (`IsAdminUser`).

---

## Tests

To be written:

- The list hides inactive brands; `product_count` counts only published products.
- Detail returns 404 for unknown and inactive slugs with the same body.
- Product list: `?brand=a&brand=b` returns the union; an inactive brand's products
  are absent from the list, the detail and the facets.
- Deleting a brand that has products raises `ProtectedError` → 409 through the
  handler.
- Query count of the product list does not grow with the number of brands.

---

## Files

```text
apps/catalog/
├── models.py
├── filters.py
├── selectors.py
├── serializers.py
├── views.py
├── urls.py
└── tests/test_brands.py
```
