# Brands

Status: Implemented

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

## Implemented

- `apps/catalog/models.py` — `Brand` exactly as planned; `Product.brand` is a required
  `PROTECT` foreign key with `related_name="products"`.
- `apps/catalog/selectors.py` — `VISIBLE_PRODUCT = Q(is_published=True,
  brand__is_active=True)` scopes `list_published_products` and
  `get_published_product_by_slug`, both of which `select_related("brand",
  "category")`. `list_active_brands` / `get_active_brand_by_slug` annotate
  `product_count` with `Count("products", filter=Q(products__is_published=True))`.
- `apps/catalog/filters.py` — `ProductFilter.brand`, a `ModelMultipleChoiceFilter`
  on `brand__slug` (subclassed as `SlugMultipleChoiceFilter` only to give
  drf-spectacular an array-of-strings schema).
- `apps/catalog/serializers.py` — `BrandSummarySerializer` (`name`, `slug`) nested in
  every product item; `BrandSerializer` for the brand endpoints.
- `apps/catalog/views.py`, `urls.py` — `BrandViewSet` (read-only, slug lookup,
  `AllowAny`, `catalog` throttle scope, unpaginated), registered as `brands`.
- `apps/catalog/services.py` — `decrement_variant_stock` treats a variant whose brand
  is inactive exactly like an unpublished one: `422 variant_unavailable` at checkout.
- `apps/catalog/admin.py` — `BrandAdmin`; `ProductAdmin` lists and filters by brand.
- `apps/catalog/management/commands/seed_demo.py` — eight seeded brands, each with a
  generated PNG logo.
- Writes through the admin API: see `admin-api.md`.

---

## Remaining

None.

---

## Decisions

### Decision: an inactive brand's variants cannot be bought

**Decision**

`decrement_variant_stock` rejects variants of an inactive brand with
`variant_unavailable`, alongside unpublished products.

**Reason**

The brand hides its products from every public endpoint; a stale cart must not be
able to buy something the storefront can no longer show.

**Consequence**

Deactivating a brand immediately stops its sales. Pending orders are unaffected.

---

## Gotchas

- `?brand=` validates slugs against every brand (active or not). An **unknown** slug
  is `400 validation_error`; an inactive brand's slug is accepted and matches
  nothing. `?category=`, by contrast, returns an empty page for an unknown slug.
- `product_count` counts published products only; it does not look at stock.
- `logo_url` is `null` when no logo is uploaded (`Brand.logo` is `blank=True`).
- Deleting a brand with products raises `ProtectedError`, a subclass of
  `IntegrityError`, which the exception handler already maps to `409 conflict`.

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

`apps/catalog/tests/test_brands.py`:

- The list hides inactive brands and counts only published products; ordering is
  `sort_order, name`; `logo_url` is the storage URL or `null`.
- Unknown and inactive slugs return byte-identical 404 bodies.
- Product list and detail carry `brand`; `?brand=a&brand=b` is the union.
- An inactive brand's products are absent from the list, the detail and the
  `/shades/` and `/sizes/` facets.
- Deleting a brand with products is a `ProtectedError` that the handler turns into 409.
- The product list stays at three queries with 2 or 8 brands.

`apps/orders/tests/test_checkout.py::test_a_variant_of_an_inactive_brand_returns_422`.

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
├── services.py
├── admin.py
└── tests/test_brands.py
```
