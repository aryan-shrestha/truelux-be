# Admin API

Status: Planned

Last updated: 2026-09-25

---

## Goal

Give the TrueLux admin app (`admin.truelux.com`) everything the merchant does day to
day, over HTTP: manage the catalogue, stock and images, work the order queue, and
see how the shop is doing.

---

## Scope

What is included in this implementation?

- `/api/v1/admin/` routes, staff only, in a new `apps/backoffice` app
  ([ADR 0013](../decisions/0013-the-admin-api-is-its-own-app.md))
- Dashboard summary
- Products: CRUD, publish toggle, variants (with stock), images (upload, reorder,
  set primary, delete)
- Brands, categories, shades and sizes: CRUD
- Orders: list, detail, status transitions

What is explicitly outside the scope?

- Staff user management. Superusers use `/django-admin/`.
- Bulk import or export, CSV
- Refunds, partial cancellation, order editing
- Audit log beyond the existing structured log lines

---

## Context

- Every write that has a business consequence goes through a service, per
  [ADR 0002](0002-admin-writes-go-through-the-service-layer.md). Order status changes
  use `apps/orders/services.py`. Stock changes use `set_variant_stock` in
  `apps/catalog/services.py`. New catalogue writes (create or update a product,
  variant or image, promote a primary image) are added to
  `apps/catalog/services.py` and are also used by the Django admin.
- Image uploads go to Cloudinary **outside** `transaction.atomic()`, per
  `media-storage.md`.
- Reads live in `apps/backoffice/selectors.py` and use `select_related` and
  `prefetch_related`. Admin list endpoints must not N+1.
- Error envelope, pagination (`limit`/`offset`, max 100) and money-as-string rules
  are unchanged from `architecture.md`.
- The Django admin moves from `/admin/` to `/django-admin/`, so `/admin` is never
  confused with the admin app.

---

## Planned

### Permissions and plumbing

- Every view: `authentication_classes = [JWTAuthentication]`,
  `permission_classes = [IsAuthenticated, IsAdminUser]`, throttle scope `admin`
  (`DJANGO_THROTTLE_ADMIN`, `2000/hour`).
- `apps/backoffice/{urls,views,serializers,selectors,tests}`. The app has no models.

### Order status flow (COD)

`pending → confirmed → shipped → delivered`, with `cancelled` reachable from
`pending` and `confirmed`. [ADR 0011](../decisions/0011-cash-on-delivery-only.md)
renames `paid` to `confirmed`: under COD, the merchant confirms the order by phone,
and cash is collected at delivery. Cancellation restores stock (ADR 0004, unchanged).

---

## API

All paths are relative to `/api/v1/admin/`. Money fields are decimal strings. IDs are
UUIDs. List endpoints marked *paginated* use the standard envelope. Taxonomy lists
return bare arrays.

### Dashboard: `GET dashboard/`

```json
{
  "orders_by_status": { "pending": 4, "confirmed": 2, "shipped": 3, "delivered": 40, "cancelled": 1 },
  "revenue": { "today": "5400.00", "last_7_days": "48200.00", "last_30_days": "190350.00" },
  "sales_by_day": [{ "date": "2026-09-01", "orders": 3, "revenue": "9600.00" }],
  "recent_orders": [ /* 5 × order list item */ ],
  "low_stock": [
    { "variant_id": "uuid", "product_id": "uuid", "product_name": "Silk Foundation",
      "sku": "LUM-SF-30-WB", "size": "30 ml", "shade": "Warm Beige", "stock_quantity": 2 }
  ]
}
```

- Revenue sums `total` of orders not `cancelled`, by `created_at` in `Asia/Kathmandu`.
- `sales_by_day` holds 30 entries, oldest first, zero-filled.
- `low_stock` lists variants with `stock_quantity <= LOW_STOCK_THRESHOLD` (5, a
  constant in `apps/backoffice/constants.py`), lowest first, at most 10.

### Products

| Method | Path | Notes |
|---|---|---|
| GET | `products/` | paginated. `search` (name, SKU), `brand` (id), `category` (id), `is_published`, `low_stock=true`, `ordering` (`name`, `base_price`, `created_at`, `-…`) |
| POST | `products/` | creates a product. Variants and images are added afterwards |
| GET | `products/{id}/` | full representation |
| PATCH | `products/{id}/` | any writable field |
| DELETE | `products/{id}/` | `204`. `409 conflict` if any variant was ordered. Unpublish instead |
| POST | `products/{id}/variants/` | adds a variant |
| PATCH | `variants/{id}/` | `sku`, `size_id`, `shade_id`, `price_override`, `stock_quantity` (through `set_variant_stock`) |
| DELETE | `variants/{id}/` | `409` if ordered |
| POST | `products/{id}/images/` | `multipart/form-data`: `image` (≤ 5 MB, jpeg/png/webp), `alt_text`, `is_primary` |
| PATCH | `images/{id}/` | `alt_text`, `sort_order`, `is_primary` (promoting clears the old primary in one transaction) |
| DELETE | `images/{id}/` | `204` |

Product representation (list items omit `description`, `variants` and `images`, and
add `variant_count`, `total_stock` and `primary_image_url`):

```json
{
  "id": "uuid",
  "name": "Silk Foundation",
  "slug": "silk-foundation",
  "description": "…",
  "brand": { "id": "uuid", "name": "Lumière", "slug": "lumiere" },
  "category": { "id": "uuid", "name": "Face", "slug": "face" },
  "base_price": "3200.00",
  "is_published": true,
  "sort_order": 0,
  "variants": [
    { "id": "uuid", "sku": "LUM-SF-30-WB",
      "size": { "id": "uuid", "name": "30 ml" },
      "shade": { "id": "uuid", "name": "Warm Beige", "hex_code": "#D8A47F" },
      "stock_quantity": 12, "price_override": null, "price": "3200.00" }
  ],
  "images": [
    { "id": "uuid", "url": "https://res.cloudinary.com/…", "alt_text": "…", "sort_order": 0, "is_primary": true }
  ],
  "created_at": "2026-09-25T10:00:00Z",
  "updated_at": "2026-09-25T10:00:00Z"
}
```

Product write body: `name`, `slug` (optional; derived from `name` and made unique
when omitted), `description`, `brand_id`, `category_id`, `base_price`,
`is_published`, `sort_order`. Variant write body: `sku`, `size_id`, `shade_id`
(nullable), `stock_quantity` (≥ 0), `price_override` (nullable, > 0).

Publishing a product with no variants is rejected with
`422 product_has_no_variants`.

### Taxonomy: brands, categories, shades, sizes

| Method | Path |
|---|---|
| GET, POST | `brands/`, `categories/`, `shades/`, `sizes/` |
| PATCH, DELETE | `brands/{id}/`, `categories/{id}/`, `shades/{id}/`, `sizes/{id}/` |

The GET endpoints return bare arrays and include inactive brands. Each item carries
`id`, its model fields, and `product_count` (for categories and brands) or
`variant_count` (for shades and sizes). `slug` is optional on write. Deleting a
referenced row returns `409 conflict`. Brand `logo` uploads use `multipart/form-data`
on POST or PATCH. Category writes accept `parent_id`; a category cannot be its own
ancestor (`400 validation_error`).

### Orders

| Method | Path | Notes |
|---|---|---|
| GET | `orders/` | paginated. `status` (repeatable), `search` (order number, name, email, phone), `created_after`, `created_before` (ISO dates) |
| GET | `orders/{id}/` | detail |
| POST | `orders/{id}/transition/` | `{ "to": "confirmed" \| "shipped" \| "delivered" \| "cancelled" }` |

Order list item:

```json
{ "id": "uuid", "order_number": "TL-000123", "status": "pending", "full_name": "Sita Sharma",
  "phone": "98XXXXXXXX", "total": "5400.00", "item_count": 2, "created_at": "…" }
```

Detail adds `email`, `address_line`, `city`, `district`, `note`, `subtotal`,
`shipping_fee`, `payment_method`, `allowed_transitions` (a list of statuses), and
`items` (`product_name`, `sku`, `variant_size`, `variant_shade`, `quantity`,
`unit_price`, `line_total`).

Transition errors: `422 invalid_status_transition`, `order_already_shipped` or
`order_not_cancellable`, as raised by the services.

---

## Data changes

None in `apps/backoffice`. `OrderStatus.PAID` becomes `CONFIRMED`
(`"confirmed"`). Migrations are regenerated from scratch.

---

## Permissions

Staff only: `IsAdminUser` on every route. Anonymous requests get `401`; non-staff
tokens get `403`.

---

## Tests

To be written, in `apps/backoffice/tests/`:

- Every route: anonymous is 401, a non-staff token is 403.
- Product CRUD round trip; slug auto-generation and uniqueness; deleting an ordered
  product is 409; publishing with no variants is 422.
- Variant stock edit goes through `set_variant_stock` (mocked assertion) and rejects
  negative values.
- Image upload uses file storage in tests; promoting a primary clears the old one;
  a file over 5 MB or of the wrong type is 400.
- Taxonomy CRUD; deleting a referenced shade or brand is 409; a category cycle is 400.
- Order list filters; each transition path; invalid transitions return the
  documented codes; cancel restores stock.
- The dashboard's revenue excludes cancelled orders; `sales_by_day` has 30
  zero-filled entries; low stock is ordered and capped.
- Query-count assertions on product and order lists.

---

## Files

```text
apps/backoffice/
├── apps.py
├── constants.py
├── selectors.py
├── serializers.py
├── views.py
├── urls.py
└── tests/
apps/catalog/services.py   # new product, variant and image writes
```
