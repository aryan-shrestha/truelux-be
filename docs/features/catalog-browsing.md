# Catalog browsing

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Let the Next.js storefront list, filter, sort, search and display products, brands
and filter facets without authentication, and without leaking anything the merchant
has not published.

---

## Scope

What is included in this implementation?

- `GET /api/v1/products/` (paginated, filterable, orderable, searchable) and
  `GET /api/v1/products/{slug}/`
- `GET /api/v1/categories/` (the tree), `GET /api/v1/brands/`,
  `GET /api/v1/brands/{slug}/`, `GET /api/v1/shades/`, `GET /api/v1/sizes/`
- A dedicated `catalog` throttle scope
- Query shapes that stay constant regardless of result count

What is explicitly outside the scope?

- Writes (see `admin-api.md`), faceted search engines, recommendations,
  personalisation, cursor pagination

---

## Context

Every endpoint here is `AllowAny`, so every serialised field is public.
`product-catalog.md` defines the models; `brands.md` and `shades-and-sizes.md` own
the brand, shade and size endpoints in detail. Visibility is one rule, in
`apps/catalog/selectors.py`: a product is public when `is_published=True` and
`brand__is_active=True` (`VISIBLE_PRODUCT`).

---

## Implemented

- `apps/catalog/selectors.py` — `list_published_products` (annotates `in_stock`,
  `select_related("brand", "category")`, prefetches images, orders by
  `sort_order, -created_at, pk`), `get_published_product_by_slug` (adds a variant
  `Prefetch` with `select_related("size", "shade")`, ordered by size then shade),
  `list_category_tree`, `list_active_brands`, `get_active_brand_by_slug`,
  `list_shades_in_use`, `list_sizes_in_use`.
- `apps/catalog/filters.py` — `ProductFilter`: `brand` (repeatable slug),
  `category` (slug), `size` and `shade` (slug, variant join with `.distinct()`),
  `min_price`, `max_price`, `in_stock`; `DeterministicOrderingFilter` appends `pk`.
- `apps/catalog/serializers.py` — list items carry `id`, `name`, `slug`,
  `base_price`, `brand` (`name`, `slug`), `category`, `primary_image`, `in_stock`;
  detail adds `description`, `images`, `variants` (`id`, `size`, `shade` or `null`,
  `price`, `in_stock`). No `stock_quantity` anywhere.
- `apps/catalog/views.py`, `urls.py` — `ProductViewSet` and `BrandViewSet`
  (read-only, slug lookups), `CategoryListView`, `ShadeListView`, `SizeListView`
  (unpaginated arrays). All `AllowAny` with the `catalog` scope
  (`DJANGO_THROTTLE_CATALOG`, `600/hour`).

---

## Remaining

None.

---

## Decisions

### Decision: `in_stock` is an annotation, not a prefetch

**Decision**

The list annotates `in_stock` with an `Exists` subquery.

**Reason**

The card needs one boolean; prefetching every variant would pull the stock table
across the network to Supabase. The list is three queries at any page size.

### Decision: taxonomy endpoints are unpaginated bare arrays

**Decision**

`/categories/`, `/brands/`, `/shades/` and `/sizes/` set `pagination_class = None`.

**Reason**

Navigation and filter pickers are useless truncated, and each list is a few dozen
rows. Clients must not expect the pagination envelope on them.

### Decision: a missing row returns 404 from the exception handler

**Decision**

Selectors let `DoesNotExist` propagate; `api_exception_handler` maps
`ObjectDoesNotExist` to `404 not_found`.

**Reason**

Unknown and hidden rows become the same 404, which is what ADR 0003 needs for orders
and what inactive brands need here.

---

## Gotchas

- `?size=` and `?shade=` join variants and need `.distinct()`; `?in_stock=` does not.
  `ordering_fields` must stay local columns, because PostgreSQL rejects `DISTINCT`
  ordered by an unselected expression.
- `?brand=` with an **unknown** slug is `400 validation_error`; `?category=` with an
  unknown slug is an empty page.
- `is_published` and `is_active` are not privacy: Cloudinary URLs stay public.
- Detail lookup is by slug, the deliberate exception to UUID lookups.
- `ProductViewSet.get_object` is overridden so detail gets the variant prefetch.
- Route names are namespaced: `reverse("v1:product-list")`.
- `primary_image` falls back to the first image when none is primary.

---

## API

```text
GET /api/v1/products/?brand=lumiere&brand=aurum&category=face&shade=warm-beige&in_stock=true&ordering=-created_at&search=serum
GET /api/v1/products/{slug}/
GET /api/v1/categories/
GET /api/v1/brands/        GET /api/v1/brands/{slug}/
GET /api/v1/shades/        GET /api/v1/sizes/
```

List item:

```json
{
  "id": "…",
  "name": "Silk Foundation",
  "slug": "silk-foundation",
  "base_price": "3200.00",
  "brand": { "name": "Lumière", "slug": "lumiere" },
  "category": { "name": "Face", "slug": "face" },
  "primary_image": { "url": "…", "alt_text": "Lumière Silk Foundation" },
  "in_stock": true
}
```

Detail variant:

```json
{ "id": "…", "size": { "name": "30 ml", "slug": "30-ml" },
  "shade": { "name": "Warm Beige", "slug": "warm-beige", "hex_code": "#D8A47F" },
  "price": "3200.00", "in_stock": true }
```

Categories: `[{ "name": "Makeup", "slug": "makeup", "children": [{ "name": "Face", "slug": "face" }] }]`.

Errors: `404 not_found` for an unknown or hidden slug; `400 validation_error` for a
bad filter value; `429 throttled`.

---

## Data changes

None; see `product-catalog.md`, `brands.md` and `shades-and-sizes.md`.

---

## Permissions

`AllowAny` on every endpoint, declared on each view.

---

## Tests

- `apps/catalog/tests/test_api.py` — list and detail, unpublished products hidden,
  404s, constant query counts (list 3, detail 3), no `stock_quantity`, every filter,
  search, deterministic ordering, variant ordering, the category tree, no write
  routes, the throttle and its separation from `anon`.
- `apps/catalog/tests/test_brands.py`, `test_shades_and_sizes.py` — brand and facet
  endpoints and filters.

---

## Files

```text
apps/catalog/{selectors,filters,serializers,views,urls}.py
apps/catalog/tests/{test_api,test_brands,test_shades_and_sizes}.py
```
