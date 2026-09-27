# Architecture

Last updated: 2026-09-26

This document describes the current architecture of the system.

It should describe durable architectural facts, not implementation history or a
tutorial for the entire codebase.

---

## System overview

The TrueLux API: a Django REST Framework JSON API for a multi-brand cosmetics
store. It serves two clients: the public Next.js storefront (anonymous, guest
checkout, cash on delivery) and the Next.js admin app (staff, JWT held server-side,
ADR 0012). It is stateless: every piece of durable state lives in a managed service
outside the running container.

```text
Storefront (browser)      Admin app (Next.js server)
          ↘                  ↙

Render (TLS termination, HTTP proxy)
  ↓
Gunicorn / Django / DRF
  ↓
Domain apps (views → services / selectors)
  ↓
Supabase PostgreSQL          Cloudinary
 ├── domain tables             └── image assets
 └── django_cache (throttle counters, ADR 0014)
```

Three properties define this architecture:

- **The filesystem is ephemeral.** Render replaces the container on every deploy and
  may restart it at any time. Nothing may be written to local disk and expected to
  survive. All uploaded images go to Cloudinary. Every upload is made by staff:
  product images and brand logos through the admin API (`multipart/form-data`) or
  the Django admin. There is no customer-facing upload endpoint.
- **There is no task queue.** Every unit of work completes inside the request that
  started it.
- **The database is external and pooled.** Connections traverse Supabase's pooler,
  which constrains how Django may use them (see External systems).

---

## Application structure

```text
config/
    settings/       base.py | local.py | production.py | test.py
    urls.py
    wsgi.py
apps/
    core/
    users/
    catalog/
    orders/
    payments/
    backoffice/
docs/
    architecture.md
    features/
```

### `apps/core`

Infrastructure shared by every domain app:

- abstract base models (`TimeStampedModel`, UUID primary key base)
- the DRF exception handler and error envelope
- pagination classes
- reusable permissions (`IsOwnerOrAdmin`)
- JSON logging and the request-id middleware
- the health endpoints

Nothing with a business meaning belongs here. `core` must not import from any
domain app; the dependency only runs the other way. A model that represents
something a user would recognise belongs in a domain app even if two apps use it.

### `apps/users`

Owns the custom user model (email as the login identifier). It is the only app
permitted to write to the user table.

Its API surface is `/api/v1/auth/`: SimpleJWT token issue, refresh with rotation
and blacklist, logout and `me`, for **staff only** (`docs/features/staff-auth.md`).
Checkout is guest-only, so there are no customer accounts and no registration.
Superusers also sign in to the Django admin at `/django-admin/` with a session.

### `backoffice`

The staff admin API under `/api/v1/admin/` (ADR 0013). It owns no models: it reads
through its own selectors and writes only through the services of `catalog` and
`orders`. Every view inherits `StaffAPIView` (JWT only, `IsAdminUser`, `admin`
throttle scope). See `docs/features/admin-api.md`.

### `catalog`, `orders`, `payments`

One app per bounded piece of the product, named for the thing it owns. A domain app
owns its models, its endpoints, and the rules for changing its data. Cross-app
writes go through the owning app's service layer, never through its models
directly.

`catalog` owns `brand`, `size`, `shade`, `category`, `product`, `product_variant`
and `product_image`. `orders` owns `order`, `order_item` and the one-row
`shipping_settings` (ADR 0017). `payments` owns the cash-on-delivery `payment`
record; there is no gateway (ADR 0011).

One boundary is genuinely non-obvious. Placing an order decrements variant stock,
and that row belongs to `catalog`. The decrement — including its
`select_for_update()` — goes through `apps.catalog.services`, never through
`ProductVariant.objects` from inside an orders service. The lock belongs on the
side that owns the row.

---

## Request flow

```text
HTTP request
    ↓
Render proxy (adds X-Forwarded-Proto)
    ↓
URL routing (/api/v1/...)
    ↓
Authentication (JWT; none for public routes) → Permissions
    ↓
View
    ↓
Serializer validation
    ↓
Service (write) / Selector (read)
    ↓
Model / Supabase PostgreSQL
    ↓
Serializer
    ↓
HTTP response
```

Deviations from this flow:

- **Image upload.** A multipart admin request assigns a file to an `ImageField`;
  saving it uploads the bytes to Cloudinary synchronously, inside the request.
  `add_product_image` uploads before it opens its transaction.
- **Health endpoints.** `/health/` and `/health/ready/` bypass authentication and
  the service layer. `/health/` returns without touching the database so that a
  database outage does not cause Render to recycle a healthy container.
- **Schema endpoints.** `/api/schema/` and the docs UI are generated by
  drf-spectacular and do not pass through the layers above. A plain `APIView` has
  no `serializer_class` for drf-spectacular to read, so it must declare its
  request and responses with `@extend_schema`; otherwise the endpoint is silently
  left out of the schema with only a logged "unable to guess serializer".
  `apps/core/tests/test_schema.py` runs `spectacular --fail-on-warn --validate`
  so that failure reaches the test suite instead of the deploy logs.

---

## Layer boundaries

### Views

Responsibility: translate HTTP to a single call into the domain and back. Parse and
validate input via a serializer, call one service or selector, serialize the result,
return a status code.

Restrictions: no queries, no business rules, no branching on domain state. A view
containing an `if` about what the data _means_ belongs in a service.

### Serializers

Responsibility: define the wire format. Validate the shape, types, and
field-level rules of input; render output.

Restrictions: no database queries, no `.save()` that performs business logic, no
cross-object rules. Serializers are used by services, not the reverse.

### Services

Responsibility: all writes and all business rules. Own transaction boundaries. Take
plain Python arguments and return models or plain data.

Restrictions: must not accept a `request`, a serializer, or anything else
HTTP-shaped. Must not return a `Response`. Must not call Cloudinary from inside an
`atomic()` block.

### Selectors

Responsibility: all reads. Build querysets, including `select_related`,
`prefetch_related`, filtering, and ordering. Apply visibility rules, so a caller
cannot accidentally read rows it should not see.

Restrictions: no writes. Must return a fully-shaped queryset or object — never a
lazy queryset that a serializer then decorates with further queries.

### Models

Responsibility: the data and its invariants. Fields, relations, `constraints`,
`indexes`, and small derived properties that depend only on the instance.

Restrictions: no cross-object orchestration, no external calls, no signals for
business logic. Constraints and indexes are declared on the model so they are
visible where the data is defined, not only in a migration.

---

## Authentication and authorization

**Authentication.** JWT via `djangorestframework-simplejwt` is the only DRF
authentication class. `POST /api/v1/auth/token/` issues an access/refresh pair to
active staff only (`USER_AUTHENTICATION_RULE = apps.users.authentication.is_active_staff`);
the admin app's server keeps them and sends `Authorization: Bearer <access>`
(ADR 0012). Refresh tokens rotate and the previous one is blacklisted, so logout is
a real server-side revocation. The Django admin keeps its own session login. The
user model uses email as `USERNAME_FIELD`; there is no username.

**Supabase Auth is not used.** Django is the sole identity provider. The Supabase
project's `auth` schema is inert and must stay that way.

**Permissions.** `IsAuthenticated` is the project-wide default; every public
endpoint opts out explicitly with `AllowAny`. Staff endpoints add `IsAdminUser`:
anonymous requests get 401, non-staff tokens 403.

**Object-level authorization.** Selectors scope querysets to what the caller may
see, so list endpoints cannot leak rows.

> **Superseded by [ADR 0003](decisions/0003-guest-checkout-with-opaque-order-access-tokens.md).**
> This section described `IsOwnerOrAdmin` (in `apps/core`) checking
> the object on detail endpoints, and an ownership rule under which a row with a
> `user` foreign key is readable only by that user. Phase 1 has no customer
> accounts and no row carries a `user` foreign key, so **no view uses that
> permission class** — it and its tests exist, unwired. What stands in for it is
> possession of `Order.access_token`; staff routes use `IsAdminUser`.

**Row Level Security is not an authorization layer here.** Django connects with a
role that bypasses RLS. Authorization lives in selectors and permission classes;
adding an RLS policy would not protect this API and must not be relied on.

---

## Data architecture

```text
User                      (apps/users)
 ├── email (unique, login identifier)
 ├── is_active / is_staff
 ├── first_name / last_name
 └── Profile (1:1, user_profiles)
      ├── display_name
      └── avatar → Cloudinary

Brand                     (apps/catalog, ADR 0009)
 ├── name, slug (unique), description, logo → Cloudinary
 └── is_active                     inactive hides the brand and its products

Category                  (apps/catalog)
 └── parent (self, SET_NULL)       a service rejects cycles

Size                      (apps/catalog)
 └── name, slug, sort_order        volume or weight, see ADR 0007

Shade                     (apps/catalog, ADR 0010)
 └── name, slug, hex_code (#RRGGBB check), sort_order

SkinType                  (apps/catalog)
 └── name, slug, sort_order        deleting one detaches it from products

Product                   (apps/catalog)
 ├── brand (PROTECT) / category (PROTECT)
 ├── base_price, is_published      publishing needs a variant
 ├── skin_types (M2M, optional), skin_feel, key_ingredients
 ├── ProductVariant (CASCADE)      the sellable unit, see ADR 0001
 │    ├── size (PROTECT) / shade (PROTECT, nullable)
 │    ├── unique (product, size, shade) NULLS NOT DISTINCT
 │    ├── sku (unique), stock_quantity
 │    └── price_override (nullable)
 └── ProductImage (CASCADE)
      ├── image → Cloudinary
      └── is_primary (one per product)
```

A product is visible to the public API only when `is_published` and its brand
`is_active` (`VISIBLE_PRODUCT` in `apps/catalog/selectors.py`); checkout refuses a
hidden variant with `variant_unavailable`.

`ProductVariant.stock_quantity` is the only column two apps write. `orders`
reaches it exclusively through `apps.catalog.services.decrement_variant_stock`
and `restore_variant_stock`, which take the whole cart and lock every row in one
ascending-`pk` `select_for_update(of=("self",))`. See ADR 0004.

Conventions that apply to every model:

- UUID primary keys, so identifiers can be generated before insert and reveal
  nothing about row counts.
- `created_at` / `updated_at` from `TimeStampedModel`.
- Uniqueness and value rules as database `constraints`, not only serializer
  validation, so a concurrent request cannot slip past them.
- `on_delete` chosen explicitly per relation. `CASCADE` only where the child is
  meaningless without the parent.
- Image fields store a Cloudinary reference, never bytes and never a local path.

Order                     (apps/orders)
 ├── order_number (unique, from a Postgres sequence)
 ├── access_token (unique, the credential, see ADR 0003)
 ├── status (pending → confirmed → shipped → delivered; cancelled), payment_method (cod)
 ├── email / phone / address columns   denormalised snapshot, no user FK
 └── OrderItem (CASCADE)
      ├── variant (PROTECT)
      └── product_name / variant_size / variant_shade / sku / unit_price
                                        snapshots, see orders.md

ShippingSettings          (apps/orders, one row, id = 1; ADR 0017)
 └── inside_valley_fee / outside_valley_fee / free_shipping_threshold (nullable)

`Order` has **no `user` foreign key**, deliberately and not as an oversight: ADR
0003 makes possession of `access_token` the authorization story for Phase 1.

Payment                   (apps/payments)
 ├── order (PROTECT)                  a payment outlives any tidying of orders
 └── method (cod) / status (pending, completed) / amount

Checkout records a pending COD payment; staff mark the cash collected. Order status
is not tied to it (ADR 0011).

---

## External systems

| System              | Purpose                                    | Integration point                                                   | Important constraint                                                                                                                                                                       |
| ------------------- | ------------------------------------------ | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Supabase PostgreSQL | Primary database, the only source of truth | Django ORM over `DATABASE_URL`; migrations over `DATABASE_DIRECT_URL`; both in the `DATABASE_SCHEMA` schema | Runtime uses the pooler; migrations need the direct connection. Pooled connections forbid server-side cursors and prepared statements, so both are disabled. TLS required. |
| Cloudinary          | Storage and CDN delivery of user images    | Django `STORAGES["default"]` via `cloudinary-storage`; `ImageField` | Upload is synchronous and inside the request. Deleting a row does not delete the asset. Delivery URLs are public.                                                                          |
| Render              | Hosting, TLS, deploys                      | Native Python service (`render.yaml`); gunicorn; uv from `uv.lock`  | Ephemeral filesystem. TLS terminates at the proxy, so Django must trust `X-Forwarded-Proto`. No scheduler, and the free instance sleeps when idle.                                         |

**Supabase usage is limited to Postgres.** Storage, Realtime, Edge Functions, and
the Supabase client libraries are not used. Images are Cloudinary's job; adding a
second object store would split ownership of the same concern.

**Deployment shape.** A native Python service, described by `render.yaml` rather
than by a dashboard. The build installs from `uv.lock`, migrates, creates
the cache table, and collects static files, which WhiteNoise then serves. All configuration arrives as
environment variables, and the blueprint is the only place the production set is
written down — two tests in `tests/test_settings.py` keep it in step with
`base.py`, because a variable declared in one and not the other is a deploy that
builds and then fails at import. See
[features/deployment.md](features/deployment.md).

**Migrations run once per deploy, in the build command**, never at application
boot, so two starting instances cannot race each other. Render's
`preDeployCommand` is the better home and needs a paid instance type; the build
command runs exactly once per deploy too, so the race is still excluded. What it
does not give is ordering against a failed release: migrations apply before the
new version is known good, so each must be compatible with the release before it.

**`ALLOWED_HOSTS` gains the Render hostname in `production.py`**, appended from
`RENDER_EXTERNAL_HOSTNAME`. Without it every request — the platform health check
included — is a `400 DisallowedHost`, which reads as an application crash rather
than a configuration mistake. `DJANGO_ALLOWED_HOSTS` still carries any custom
domain.

---

## Caching

Django's `DatabaseCache`, in the `django_cache` table, backs the **throttle
counters** and nothing else (ADR 0014). `createcachetable` builds the table in the
Render build and in `make migrate`; `/health/ready/` fails if it is missing. Each
throttled request costs a few extra queries, the price ADR 0014 accepts for having
no Redis. **No selector caches a query.** The test settings use local memory so
query-count tests measure only the endpoint.

Rules, for when something is cached:

- Cache keys are versioned and namespaced by concern: `v1:<domain>:<identifier>`.
  Bump the version prefix rather than writing a migration to clear keys.
- Every entry has an explicit TTL. No indefinite entries.
- Invalidation is the responsibility of the service that performs the write, in the
  same function as the write.
- A cache miss or a cleared cache table must never change a response's
  correctness — only its latency.

**Sessions and authentication state are not cached.** JWT is stateless and the
token blacklist is its own database table.

---

## Transactions and consistency

- Services own transaction boundaries with explicit `transaction.atomic()`.
  `ATOMIC_REQUESTS` is off, so a transaction covers the write it belongs to rather
  than the whole request.
- Placing an order is atomic across the order row, its items, and the stock
  decrement on every variant in the cart. An order that did not reserve stock is
  not a valid state.
- **Cloudinary uploads must not happen inside `atomic()`.** An upload can take
  seconds; holding a pooled Supabase connection open for that duration exhausts the
  pool under load. Upload first, then open the transaction to persist the reference.
- Consequence, accepted deliberately: if the transaction fails after a successful
  upload, the asset is orphaned in Cloudinary. Orphaned assets are harmless; a
  database row pointing at a missing image is not, and this ordering prevents that.
- Uniqueness is enforced by database constraints, and services catch
  `IntegrityError` and convert it into a domain error. A check-then-insert in Python
  is a race, not a validation.
- `CONN_MAX_AGE` is 0. Supavisor already pools; a second pool in Django holds pooler
  slots open and starves other instances.
- `DISABLE_SERVER_SIDE_CURSORS` is `True`. A pooled connection cannot be relied on
  to hold a cursor across statements, so leaving this unset produces
  `InvalidCursorName` errors under load that never reproduce against a local
  Postgres. Set regardless of which pooler port a deployment uses, because the
  code must not depend on which one it got.

---

## Error handling

A single exception handler in `apps/core` converts every failure into one envelope,
so clients parse one shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Enter a valid email address.",
    "details": { "email": ["Enter a valid email address."] }
  }
}
```

| Condition                                               | Status    | `code`                              |
| ------------------------------------------------------- | --------- | ----------------------------------- |
| Request body was not valid JSON                         | 400       | `parse_error`                       |
| Serializer or field validation failed                   | 400       | `validation_error`                  |
| Missing or invalid credentials                          | 401       | `authentication_failed`             |
| Authenticated but not permitted                         | 403       | `permission_denied`                 |
| Object absent, or present but not visible to the caller | 404       | `not_found`                         |
| Method not allowed on this route                        | 405       | `method_not_allowed`                |
| No representation matching the `Accept` header          | 406       | `not_acceptable`                    |
| Write conflicted with a database constraint             | 409       | `conflict`                          |
| `Content-Type` not supported by this endpoint           | 415       | `unsupported_media_type`            |
| Business rule rejected the request                      | 422       | the `DomainError` subclass's `code` |
| Throttled                                               | 429       | `throttled`                         |
| Anything unhandled                                      | 500       | `server_error`                      |
| Any other DRF exception                                 | as raised | `error`                             |

Rules:

- Domain errors are exceptions raised by services, not tuples or `None` returns.
  The handler maps them; services never build HTTP responses.
- Every code above is stated explicitly in `_PUBLISHED_CODES` in
  `apps/core/exceptions.py`, never read from DRF's `exc.default_code`. `default_code`
  belongs to DRF: an upgrade that renames one would otherwise change this API's
  public contract with nothing failing until a client broke. Two already disagree —
  DRF spells them `invalid` and `not_authenticated`.
- A DRF exception with no row above reports the generic `error`, keeping its own
  status, rather than leaking whatever DRF calls it internally. Adding such an
  exception to the API surface means adding a row here and to `_PUBLISHED_CODES`.
- A hidden object returns 404, not 403, so the API does not confirm that an
  identifier exists to someone not entitled to know.
- 500 responses carry no exception text. The detail goes to the logs with the
  request id.
- Every log line and every response carries a request id, so a client-reported
  failure can be found in Render's logs. CORS exposes `X-Request-ID` so browser
  clients can read it.

---

## Important constraints

Future implementation must preserve these:

- **No Celery, no task queue, no background worker.** Work that cannot complete
  inside a request needs an architectural decision, not a library.
- **Nothing is written to the local filesystem.** The container is disposable.
- **Cloudinary is the only store for uploaded files.** Only the admin API's image
  and brand-logo endpoints accept `multipart/form-data`; every other route is JSON.
- **Supabase is used as Postgres only.** No Supabase Auth, Storage, or client SDK.
- **Django authorization is the only authorization.** RLS is bypassed by design.
- **The cache is never a source of truth.**
- **`/api/v1/admin/` is staff-only, JWT-only**, and never writes a model directly.
- **All writes go through services; all reads go through selectors.**
- **Migrations run once per deploy, in the build command**, never at boot and never
  automatically on request.
- **`/api/v1/` responses stay backward compatible.** Breaking changes get `/api/v2/`.
- **Every model change ships with its migration** in the same commit.

---

## Known architectural limitations

- **Image uploads occupy a worker.** A large upload holds a gunicorn worker for its
  full duration, and there is no queue to move it to. On a small Render instance
  this measurably reduces concurrency. Mitigation if it becomes a problem: upload
  directly from the client to Cloudinary with a signed upload preset, and have the
  API accept only the resulting reference.
- **Deleted rows leave Cloudinary assets behind.** Nothing reconciles the two
  stores. Storage grows monotonically with deletions.
- **Cloudinary URLs are public.** Anyone with a URL can fetch the asset,
  indefinitely. Any genuinely private image would need signed, expiring delivery
  URLs, which is not implemented.
- **Connection pooling rules out streaming large result sets.** Server-side cursors
  are disabled, so `.iterator()` still materialises the full result. Large exports
  must be paginated in application code.
- **No scheduled work is possible in-process.** Anything periodic requires an
  external trigger calling an authenticated endpoint.
- **Cold starts.** On Render's lower tiers the service sleeps when idle; the first
  request afterwards pays the container start plus Django boot.
- **Region latency is unhedged.** Render and Supabase are in one region each, and
  every query crosses the network between them. An N+1 that is invisible locally is
  expensive in production.
- **Throttling costs database writes.** Every throttled request reads and writes
  `django_cache`, and nothing prunes it except Django's own culling.
