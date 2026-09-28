# Features

Current feature inventory.

TrueLux is a multi-brand cosmetics store. The API serves a public Next.js storefront
(guest checkout, cash on delivery only) and a Next.js admin app for staff
(`/api/v1/admin/`, JWT held server-side). The Django admin at `/django-admin/`
remains for superusers. The codebase was forked from a clothing store; Khalti and
Redis were removed at the fork.

| #   | Feature             | Status      | Documentation                     | Depends on | Last updated |
| --- | ------------------- | ----------- | --------------------------------- | ---------- | ------------ |
| 1   | staff-identity      | Implemented | `features/staff-identity.md`      | —          | 2026-09-25   |
| 2   | api-error-contract  | Implemented | `features/api-error-contract.md`  | 1          | 2026-09-28   |
| 3   | media-storage       | Implemented | `features/media-storage.md`       | —          | 2026-09-25   |
| 4   | product-catalog     | Implemented | `features/product-catalog.md`     | 2, 3       | 2026-09-26   |
| 5   | catalog-browsing    | Implemented | `features/catalog-browsing.md`    | 4          | 2026-09-26   |
| 6   | orders              | Implemented | `features/orders.md`              | 2, 4       | 2026-09-25   |
| 7   | checkout            | Implemented | `features/checkout.md`            | 6, 19      | 2026-09-27   |
| 8   | payments            | Implemented | `features/payments.md`            | 7          | 2026-09-25   |
| 9   | transactional-email | Implemented | `features/transactional-email.md` | 6          | 2026-09-25   |
| 10  | merchant-admin      | Implemented | `features/merchant-admin.md`      | 4, 6, 8    | 2026-09-25   |
| 11  | demo-seed           | Implemented | `features/demo-seed.md`           | 4, 6, 8, 16, 17 | 2026-09-29 |
| 12  | deployment          | Implemented | `features/deployment.md`          | —          | 2026-09-27   |
| 13  | brands              | Implemented | `features/brands.md`              | 4, 5       | 2026-09-26   |
| 14  | shades-and-sizes    | Implemented | `features/shades-and-sizes.md`    | 4, 5, 6    | 2026-09-26   |
| 15  | staff-auth          | Implemented | `features/staff-auth.md`          | 1          | 2026-09-26   |
| 16  | admin-api           | Implemented | `features/admin-api.md`           | 4, 6, 13, 14, 15, 19 | 2026-09-28 |
| 17  | skin-types          | Implemented | `features/skin-types.md`          | 4, 5, 16   | 2026-09-26   |
| 18  | catalogue-import    | Implemented | `features/catalogue-import.md`    | 3, 4, 17   | 2026-09-26   |
| 19  | checkout-quote-and-shipping | Implemented | `features/checkout-quote-and-shipping.md` | 6, 7, 16 | 2026-09-27 |

`Depends on` refers to the `#` column of this table.

## What changed at the fork

- **Brands** (#13) and **shades** (#14) reshape the catalogue for cosmetics. Every
  product has a brand; an inactive brand hides its products everywhere, including
  checkout. A variant's shade is optional, and sizes are volumes or weights.
- **Cash on delivery only** (ADR 0011). `paid` became `confirmed`: the merchant
  confirms by phone, and the cash is recorded separately when it is collected.
- **The database cache replaces Redis** (ADR 0014). Throttle counters live in the
  `django_cache` table, created by `createcachetable` in the build and in
  `make migrate`.
- **Staff sign in over JWT** (#15, ADR 0012), and **the admin API** (#16, ADR 0013)
  gives the admin app everything the merchant does day to day. Catalogue writes are
  services shared with the Django admin (ADR 0002).
- **Skin types and care details** (#17): products carry optional skin types, a skin
  feel and key ingredients; `?skin_type=` and `/skin-types/` serve the storefront's
  shop-by-skin-type menu, and `?category=<parent>` includes the parent's children.
- Migrations were regenerated as fresh `0001_initial`s; `catalog/0002_skin_types`
  followed with skin types (#17).
- **The real catalogue loads from a workbook** (#18, ADR 0016): `import_catalogue`
  validates an Excel workbook and upserts it through the services, locally or into
  production from the owner's machine with `ENV_FILE=.env.production`.
- **Shipping is merchant data** (#19, ADR 0017). The fees and an optional
  free-shipping threshold live in a `ShippingSettings` row that staff edit at
  `/api/v1/admin/settings/shipping/`; `POST /checkout/quote/` prices a cart through
  the same `price_cart` that checkout uses, and `GET /shipping/` serves the fees.
- **A demo deploy seeds itself** (ADR 0015). With `SEED_DEMO_DATA` true, the Render
  build fills an empty database with the demo catalogue, orders and staff login.

## Contracts with the front-end apps

- The storefront must serve `/orders/<access_token>`: the confirmation email links
  there (`STOREFRONT_URL`).
- The admin app obtains tokens from `/api/v1/auth/token/`, keeps them server-side,
  and sends `multipart/form-data` for image and logo uploads. Every other write is
  JSON. The OpenAPI schema is served at `/api/schema/` (Swagger at
  `/api/schema/swagger-ui/`); the repository does not keep a generated copy.

## Not done

- **Nothing has been deployed as TrueLux.** Every claim rests on the test suite and
  a local run.
- **No email has been seen in a real client**, and no SMTP relay is configured.
- The standing duties with no automatic recovery (confirming or cancelling pending
  orders so stock is released, resending failed email) are in
  [../handover.md](../handover.md).

## Architectural decisions

| ADR  | Decision                                        | Governs                               |
| ---- | ----------------------------------------------- | ------------------------------------- |
| 0001 | The variant is the stock and SKU unit           | product-catalog, orders, checkout     |
| 0002 | Admin writes go through the service layer       | merchant-admin, admin-api             |
| 0003 | Guest checkout, with opaque access tokens       | orders, checkout                      |
| 0004 | Stock is committed at order placement           | checkout, product-catalog, orders     |
| 0005 | Khalti lookup is the only verification          | superseded by 0011                    |
| 0006 | Transactional email sends in-request            | transactional-email, checkout         |
| 0007 | Size and colour are lookup tables               | product-catalog (colour: see 0010)    |
| 0008 | Every environment variable is required          | every app; `config/settings` (its `SHIPPING_FEE_*` entries superseded by 0017) |
| 0009 | Brand is a first-class model                    | brands, catalog-browsing              |
| 0010 | Shade replaces colour, and is optional          | shades-and-sizes, orders              |
| 0011 | Cash on delivery only                           | payments, orders, checkout            |
| 0012 | The admin app authenticates with JWT server-side | staff-auth, admin-api                |
| 0013 | The admin API is its own app                    | admin-api                             |
| 0014 | The database cache replaces Redis               | deployment, every throttled endpoint  |
| 0015 | The build seeds demo data when asked            | deployment, demo-seed, staff-auth     |
| 0016 | The real catalogue is imported from a workbook  | catalogue-import, deployment          |
| 0017 | Shipping fees are merchant data                 | checkout-quote-and-shipping, checkout, admin-api |

## Deferred

Customer accounts and order history, online payment, discount codes (the quote
already returns `discount`), wishlist,
reviews, returns and refunds, staff roles, bulk import/export in the admin app (the
owner's workbook import is #18), courier tracking,
restock notifications, and a scheduler for sweeps (stale pending orders, unsent
email).

## Status definitions

- **Planned** — documented but implementation has not started.
- **In progress** — implementation has started but is incomplete.
- **Implemented** — documented scope is implemented and verified.
- **Blocked** — implementation cannot continue because of a documented blocker.
- **Deprecated** — feature exists but should not receive new development.
