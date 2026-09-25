# TrueLux — Backend

Django 5 + Django REST Framework API for TrueLux, a multi-brand cosmetics store. It
serves the public storefront (guest checkout, cash on delivery) and the staff admin
app.

Read [`CLAUDE.md`](CLAUDE.md) before your first change, then
[`docs/architecture.md`](docs/architecture.md),
[`docs/convention.md`](docs/convention.md) and
[`docs/features/index.md`](docs/features/index.md).
[`docs/handover.md`](docs/handover.md) is the merchant's runbook.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/): the virtualenv, dependencies and command runner
- PostgreSQL 15+ (`docker compose up -d` gives you 16 on port **5433**)

There is no `requirements.txt`; pip and Poetry are not used.

## From clone to a running server

```bash
docker compose up -d        # Postgres 16 on localhost:5433, database "truelux"
cp .env.example .env        # fill the four blanks: secret key (32+ chars) and the three
                            # Cloudinary values (any placeholder works locally)

make install                # uv sync
make migrate                # migrations + the django_cache table
make seed                   # 8 brands, 33 products, 17 orders (DEBUG only)
make seed-staff             # staff@truelux.com / truelux-demo-staff (from .env)
make run                    # http://localhost:8000
```

`config.settings.local` forces `DEBUG` on and the SSL redirect off, stores uploads
in `media/` and prints email to the console. Every variable in `.env.example` is
required (ADR 0008); a missing or malformed one stops startup with one error
naming all of them.

## Commands

| Command | Does |
| --- | --- |
| `make install` | Sync the virtualenv from `uv.lock` |
| `make run` | Development server on port 8000 |
| `make migrate` | Migrate and create the cache table over the direct connection |
| `make seed` / `make reseed` | Demo catalogue and orders / delete and seed again |
| `make seed-staff` | Create or reset the demo staff login |
| `make test` | pytest with coverage (80% floor) |
| `make lint` / `make format` | ruff |
| `make typecheck` | mypy (strict) |
| `make shell` / `make superuser` / `make check` | Django management |

## Endpoints

Public (storefront):

| Path | Methods | Purpose |
| --- | --- | --- |
| `/api/v1/products/` | GET | Visible products; `brand` (repeatable), `category`, `size`, `shade`, price and `in_stock` filters, search, ordering, pagination |
| `/api/v1/products/{slug}/` | GET | One product with variants (`shade` may be `null`) |
| `/api/v1/brands/`, `/api/v1/brands/{slug}/` | GET | Active brands with published product counts |
| `/api/v1/categories/` | GET | The category tree |
| `/api/v1/shades/`, `/api/v1/sizes/` | GET | Facet values used by visible products |
| `/api/v1/checkout/` | POST | Place a cash-on-delivery order |
| `/api/v1/orders/lookup/` | POST | Find an order by number and email |
| `/api/v1/orders/{access_token}/` | GET | One order; the token is the authorization |

Staff (admin app; `Authorization: Bearer <access>`):

| Path | Purpose |
| --- | --- |
| `/api/v1/auth/token/`, `/token/refresh/`, `/logout/`, `/me/` | Staff JWT login, rotation, revocation, profile |
| `/api/v1/admin/dashboard/` | Orders by status, revenue, 30-day sales, recent orders, low stock |
| `/api/v1/admin/products/` … `/variants/{id}/`, `/images/{id}/` | Catalogue CRUD, stock, images |
| `/api/v1/admin/brands/`, `/categories/`, `/shades/`, `/sizes/` | Taxonomy CRUD |
| `/api/v1/admin/orders/`, `/orders/{id}/transition/` | Order queue and status changes |

Other: `/health/`, `/health/ready/`, `/django-admin/` (superusers),
`/api/schema/` (OpenAPI, plus `/swagger-ui/` and `/redoc/`). The full contracts are
in `docs/features/`.

## Architecture

```text
config/settings/   base.py (reads every env var) | local.py | test.py | production.py
apps/core/         base models, error envelope, pagination, logging, health
apps/users/        staff users and the JWT endpoints
apps/catalog/      brands, categories, sizes, shades, products, variants, images
apps/orders/       orders, checkout, transitions, emails
apps/payments/     cash-on-delivery records
apps/backoffice/   the staff admin API (no models)
```

Requests flow **view → serializer → service (writes) / selector (reads) → model**.
Every failure returns `{"error": {"code", "message", "details"}}`.

## Deployment

Render, as the native Python service `truelux-api` described by `render.yaml`:
build runs `uv sync --frozen`, `migrate`, `createcachetable` and `collectstatic`;
Supabase Postgres and Cloudinary are the only other services. See
[`docs/features/deployment.md`](docs/features/deployment.md).
