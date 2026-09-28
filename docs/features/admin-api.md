# Admin API

Status: Implemented

Last updated: 2026-09-27

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
- Brands, categories, shades, sizes and skin types: CRUD
- Orders: list, detail, status transitions
- Shipping settings: fees and free-shipping threshold
  (`checkout-quote-and-shipping.md`)

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

## Implemented

- `apps/backoffice/` (no models): `views.py`, `serializers.py`, `selectors.py`,
  `filters.py`, `constants.py`, `urls.py`, mounted at `/api/v1/admin/` in
  `config/urls.py` and registered in `INSTALLED_APPS`.
- `StaffAPIView` is the single policy every admin view inherits:
  `JWTAuthentication` only, `IsAuthenticated` + `IsAdminUser`, `ScopedRateThrottle`
  with scope `admin` (`DJANGO_THROTTLE_ADMIN`). A test walks every route in
  `apps/backoffice/urls.py` and fails if a view does not inherit it.
- `apps/catalog/services/` is now a package (`stock.py`, `products.py`,
  `taxonomy.py`, re-exported from `__init__.py`): `create_product`, `update_product`,
  `delete_product`, `create_variant`, `update_variant`
  (stock through `set_variant_stock`), `delete_variant`, `add_product_image`,
  `update_product_image`, `delete_product_image`, and `create_taxonomy_entry`,
  `update_taxonomy_entry`, `delete_taxonomy_entry` for brands, categories, shades,
  sizes and skin types. `create_product` / `update_product` take `skin_types` and
  replace the set in the same transaction as the row (`skin-types.md`). Omitted slugs are derived from the name and suffixed `-2`, `-3`… until free.
- `apps/orders/`: `OrderStatus.CONFIRMED` replaces `PAID`; `ALLOWED_TRANSITIONS` in
  `constants.py`; `confirm_order` replaces `mark_order_paid`; `transition_order`
  dispatches to `confirm_order`, `mark_order_shipped`, `mark_order_delivered` or
  `cancel_order`, so each keeps its own error.
- The Django admin shares the services: "Publish" / "Unpublish" actions call
  `update_product` with `is_published` (read-only on the form), and
  `ProductImageAdmin`'s "Make primary" action calls `update_product_image`
  (`is_primary` is read-only there). Orders get "Mark selected orders as confirmed".
- The dashboard is one selector, `get_dashboard`, in `Asia/Kathmandu` days.
- `ShippingSettingsView` reads `apps.orders.selectors.get_shipping_settings` and
  writes through `apps.orders.services.update_shipping_settings`.

---

## Remaining

None.

---

## Decisions

### Decision: publishing and image promotion are admin actions

**Decision**

In the Django admin, `Product.is_published` and `ProductImage.is_primary` are
read-only fields changed by actions that call the catalogue services.

**Reason**

ADR 0002: a field whose change has a consequence is an action. Django 5's model
forms also validate the one-primary constraint before `save_model` runs, so a form
could never promote an image.

### Decision: FK ids are validated by the serializer

**Decision**

`brand_id`, `category_id`, `size_id`, `shade_id`, `parent_id` and `skin_type_ids`
are `PrimaryKeyRelatedField`s; services receive model instances.

**Reason**

An unknown id is a `400 validation_error` naming the field, rather than a database
foreign-key failure reported as `409 conflict`.

---

## Gotchas

- Order numbers are `TL-<year>-<6 digits>` (for example `TL-2026-000123`), from the
  existing sequence; the `TL-000123` in the examples below is illustrative.
- `item_count` is the number of units (sum of line quantities), not of lines.
- `created_after` / `created_before` are `Asia/Kathmandu` days, like the dashboard,
  so a KPI link lists exactly the orders the KPI counted. Both ends are inclusive:
  the filter is `created_at >= 00:00 NPT on created_after` and `< 00:00 NPT on the
  day after created_before`. An order at 00:30 NPT falls on the previous UTC day,
  so comparing `created_at__date` (UTC) would put it on the wrong day.
- Product `search` matches the name or any variant SKU (with `.distinct()`).
- Unique names and slugs, and a second shadeless variant of one size, are enforced
  by the database: `409 conflict`.
- A category cycle is a Django `ValidationError` from the service, which the handler
  returns as `400 validation_error` with `details.parent_id`.
- Deleting a product, variant or taxonomy row relies on `PROTECT`: `ProtectedError`
  subclasses `IntegrityError`, so the handler already answers `409 conflict`. Skin
  types are the exception: deleting one in use is `204` and detaches it.
- `skin_type_ids` on `PATCH` replaces the whole set; omit it to keep the set.
- Deleting an image deletes the row only; the stored asset is left behind.
- The staff app must send `multipart/form-data` for image uploads and brand logos;
  every other write is JSON.
- `POST products/{id}/images/` accepts only `multipart/form-data`; anything else is
  `415 unsupported_media_type`. It used to accept url-encoded bodies too, which
  cannot carry a file. On 2026-09-28 the admin's axios client (fetch adapter, on
  the server) sent a multipart body labelled `application/x-www-form-urlencoded`,
  because axios defaults POSTs to that type and only clears it for `FormData` in a
  browser. Django split the image on `&` and failed with a 500. The fix for the
  client lives in the admin repo; brand and product writes still accept url-encoded
  bodies through `JSON_AND_MULTIPART`, where that mislabelling now gets a 400
  `parse_error` rather than a 500.

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
  `shade` is the shade's name, or `null` for a shadeless variant.

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

Product representation (list items omit `description`, `skin_types`, `skin_feel`,
`key_ingredients`, `variants` and `images`, and add `variant_count`, `total_stock` and
`primary_image_url`):

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
  "skin_types": [{ "id": "uuid", "name": "Combination", "slug": "combination" }],
  "skin_feel": "Soothed, balanced, refreshed",
  "key_ingredients": "Water (Aqua), Niacinamide",
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
`is_published`, `sort_order`, `skin_type_ids` (list of UUIDs, optional),
`skin_feel` (≤ 200 characters), `key_ingredients`. Variant write body: `sku`, `size_id`, `shade_id`
(nullable), `stock_quantity` (≥ 0), `price_override` (nullable, > 0).

Publishing a product with no variants is rejected with
`422 product_has_no_variants`.

### Taxonomy: brands, categories, shades, sizes, skin types

| Method | Path |
|---|---|
| GET, POST | `brands/`, `categories/`, `shades/`, `sizes/`, `skin-types/` |
| PATCH, DELETE | `brands/{id}/`, `categories/{id}/`, `shades/{id}/`, `sizes/{id}/`, `skin-types/{id}/` |

The GET endpoints return bare arrays and include inactive brands. Each item carries
`id`, its model fields, and `product_count` (for categories, brands and skin types)
or `variant_count` (for shades and sizes). `slug` is optional on write. Deleting a
referenced row returns `409 conflict`, except a skin type, which is detached from its
products (`204`). Brand `logo` uploads use `multipart/form-data`
on POST or PATCH. Category writes accept `parent_id`; a category cannot be its own
ancestor (`400 validation_error`).

### Orders

| Method | Path | Notes |
|---|---|---|
| GET | `orders/` | paginated. `status` (repeatable), `search` (order number, name, email, phone), `created_after`, `created_before` (ISO dates, inclusive, `Asia/Kathmandu` days) |
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

### Shipping settings: `GET, PATCH settings/shipping/`

```json
{ "inside_valley_fee": "150.00", "outside_valley_fee": "250.00",
  "free_shipping_threshold": null, "updated_at": "…" }
```

`PATCH` is partial. Fees must be ≥ 0; the threshold must be > 0 or `null` (no free
shipping); otherwise `400 validation_error`. The next quote and checkout use the new
values; placed orders keep what they were charged. Full contract in
`checkout-quote-and-shipping.md`.

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

`apps/backoffice/tests/`:

- `test_permissions.py` — every route and method: anonymous is 401, a non-staff
  token is 403; every route inherits `StaffAPIView`; a Django admin session is 401.
- `test_products.py` — CRUD round trip; slug derivation and uniqueness; unknown
  brand is 400; publishing without variants is 422 on create and update; deleting
  an ordered product or variant is 409; list shape, filters and a constant three
  queries; `skin_type_ids` set, kept, replaced and cleared, unknown id 400; variant stock edits call `set_variant_stock` (mocked) and reject
  negatives; image upload, primary promotion, wrong type and >5 MB are 400; a
  non-multipart upload is 415.
- `test_taxonomy.py` — brand list includes inactive brands with counts; logo upload
  and slug derivation; shade hex validation; deleting a referenced brand, shade,
  size or category is 409; duplicate names are 409; category cycles are 400; skin
  type CRUD with `product_count`, and deleting one detaches it.
- `test_orders.py` — list shape, status/search/date filters (Kathmandu day
  boundaries, both ends inclusive), constant two queries;
  detail with `allowed_transitions` and `line_total`; each transition path; the
  documented 422 codes; cancel restores stock; `ALLOWED_TRANSITIONS` agrees with the
  services for every pair.
- `test_shipping_settings.py` — GET and partial PATCH, validation, non-staff 403,
  and a PATCH changing the next quote.
- `test_dashboard.py` — revenue excludes cancelled orders and uses the Kathmandu
  day; `sales_by_day` has 30 zero-filled days; every status is counted; five recent
  orders; low stock is lowest first and capped at ten.

`apps/catalog/tests/test_admin.py` covers the publish, unpublish and make-primary
admin actions.

---

## Files

```text
apps/backoffice/
├── apps.py
├── constants.py
├── filters.py
├── selectors.py
├── serializers.py
├── views.py
├── urls.py
└── tests/
apps/catalog/services/     # products.py, taxonomy.py, stock.py
apps/orders/constants.py   # ALLOWED_TRANSITIONS
apps/orders/services.py    # confirm_order, transition_order, update_shipping_settings
```
