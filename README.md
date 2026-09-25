# Clothing Store — Backend

Django 5 + Django REST Framework API for the clothing store.

Read [`CLAUDE.md`](CLAUDE.md) before your first change, then
[`docs/architecture.md`](docs/architecture.md) and
[`docs/convention.md`](docs/convention.md).

[`docs/handover.md`](docs/handover.md) is the merchant's runbook — how the shop is
run from the admin, and the three daily checks that have no automatic recovery. It
is written for a non-engineer, and it is the right thing to hand over at launch.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) — manages the virtualenv, dependencies, and command execution
- PostgreSQL 16 and Redis 7 (or `docker compose up -d`)

`uv` is the only supported entry point. There is no `requirements.txt`, and pip
and Poetry are not used.

## From clone to a running server

```bash
git clone <repo> && cd backend

docker compose up -d                     # local postgres + redis (optional)
cp .env.example .env                     # then fill in the five blanks it leaves

make install                             # uv sync
make migrate                             # apply migrations
make superuser                           # create a staff account
make run                                 # http://localhost:8000
```

Every variable is required and none has a default, so a missing or malformed one
raises `ImproperlyConfigured` before the server starts, naming everything that is
wrong at once. `.env.example` leaves five blanks — the Django secret key, the three
Cloudinary values and the Khalti key — and carries a working value for everything
else. Placeholders are fine locally; only real credentials reach the real services.
See [Environment](#environment).

## Commands

| Command | Does |
| --- | --- |
| `make install` | Sync the virtualenv from `uv.lock` |
| `make run` | Development server |
| `make seed` | Populate a development catalogue **and order history**. Refuses to run outside `DEBUG` |
| `make reseed` | Delete the seeded rows and seed again, in the order the foreign keys demand |
| `make test` | pytest with coverage (80% floor) |
| `make lint` | `ruff format --check` and `ruff check` |
| `make format` | Apply formatting and safe fixes |
| `make typecheck` | mypy |
| `make migrate` / `make makemigrations` | Migrations |
| `make shell` / `make superuser` / `make check` | Django management |

Run a single test with `uv run pytest path/to/test_file.py::test_name`.

## Endpoints

| Path | Methods | Purpose |
| --- | --- | --- |
| `/health/` | GET | Liveness. Touches no dependency. |
| `/health/ready/` | GET | Readiness. Checks the database and cache; 503 if either is unreachable. |
| `/api/v1/categories/` | GET | The category tree |
| `/api/v1/products/` | GET | Published products; filterable, orderable, paginated |
| `/api/v1/products/{slug}/` | GET | One product with its variants |
| `/api/v1/checkout/` | POST | Place an order. Commits stock, then hands off to the payment method |
| `/api/v1/orders/lookup/` | POST | Find an order by order number and email |
| `/api/v1/orders/{access_token}/` | GET | One order. Possession of the token is the authorization |
| `/api/v1/payments/khalti/return/` | GET | Where Khalti returns the customer. Verifies by server-side lookup |
| `/admin/` | — | The merchant back-office. In Phase 1 this is the entire staff interface. |
| `/api/schema/` | GET | OpenAPI 3 schema, plus `/swagger-ui/` and `/redoc/` |

Every `/api/v1/` route is unauthenticated: Phase 1 has no customer accounts, and
possession of an order's `access_token` is its authorization
([ADR 0003](docs/decisions/0003-guest-checkout-with-opaque-order-access-tokens.md)).
Routes are namespaced for versioning, so `reverse("v1:product-list")`.

## Architecture

```text
config/settings/   base.py (reads every env var) | local.py | test.py | production.py
apps/core/         base models, error envelope, pagination, permissions, logging, health
apps/users/        the custom user model; admin-only in Phase 1
apps/catalog/      categories, products, variants, images
apps/orders/       orders, order items, checkout, the confirmation emails
apps/payments/     payment records and the Khalti client
```

The five apps above are the complete set for Phase 1. Adding a sixth needs an ADR.

Requests flow **view → serializer → service (writes) / selector (reads) → model**.
Views hold no business rules, serializers hold no queries, services take plain
Python arguments and never see HTTP. See `docs/architecture.md` for the full rules.

### Errors

Every failure returns one envelope:

```json
{ "error": { "code": "validation_error", "message": "...", "details": {} } }
```

Clients branch on `error.code`; it is part of the public API. Status and code
pairs are tabulated in `docs/architecture.md`.

### Logging

Structured JSON on stdout, one object per line. Every line and every response
carries an `X-Request-ID`, taken from the inbound header when a proxy supplies one.

## Environment

**Every variable in [`.env.example`](.env.example) is required, in every
environment, and none has a default** ([ADR 0008](docs/decisions/0008-every-environment-variable-is-required.md)).
A variable that is missing, empty or malformed prevents the settings module from
importing — the application does not start half-configured.

The exception names every problem at once rather than the first:

```text
django.core.exceptions.ImproperlyConfigured: The environment is not configured correctly:
  - DJANGO_SECRET_KEY is not set
  - DJANGO_THROTTLE_CATALOG must be a rate like 60/hour, with a period of second, minute, hour, day
  - EMAIL_PORT must be a whole number, not 'five-eight-seven'
  - KHALTI_BASE_URL must be an http(s) URL, not 'dev.khalti.com/api/v2/'
```

Values are validated, not merely present: numbers must parse, URLs must be URLs,
throttle rates must spell their period in full, and `DJANGO_DEBUG=Tru` is an error
rather than a silent false.

Four variables may be set but left empty, because empty is a real choice there:
`DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `EMAIL_HOST_USER` and
`EMAIL_HOST_PASSWORD`.

`tests/test_settings.py` removes each variable in turn and asserts the failure, so
adding one without documenting it in `.env.example` fails the suite.

`DATABASE_URL` is the runtime connection — Supabase's pooler in production, which
serves session mode on port 5432 and transaction mode on 6543. The database
settings are written to be correct under either. Migrations cannot run over the
pooler at all, so there is a second `direct` alias fed by `DATABASE_DIRECT_URL`,
and `make migrate` runs `migrate --database=direct`.
`DATABASE_DIRECT_URL` has no default and must be set
even locally, where it is simply the same URL as `DATABASE_URL`: defaulting it to
`DATABASE_URL` would mean a production deployment that forgot it would migrate over
the pooler and fail in a way that does not look like a missing variable.

## Deployment

Render, as a **native Python web service** — not a container. `render.yaml` at the
repository root describes the whole thing: build, start, health check, and all 37
environment variables. Render detects `uv.lock` and installs with uv, and
`.python-version` pins the interpreter.

```yaml
buildCommand:  uv sync --frozen
               && manage.py migrate --database=direct
               && manage.py collectstatic --noinput
startCommand:  gunicorn config.wsgi:application --bind 0.0.0.0:$PORT ...
healthCheckPath: /health/
```

To deploy the first time: push, create a Blueprint from `render.yaml`, and fill
the **17 values Render prompts for** — the connection URLs, the Cloudinary and
Khalti credentials, the SMTP details, and the four that describe where the
storefront lives: `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`,
`DJANGO_CSRF_TRUSTED_ORIGINS` and `STOREFRONT_URL`. `DJANGO_SECRET_KEY` is
generated by Render; the remaining 19 carry values from the blueprint.

Getting the CORS list wrong is the one misconfiguration that boots cleanly and
still breaks the storefront, with nothing in the backend logs to say so.

Migrations run in the build command because the free instance type has no
`preDeployCommand`. They still run once per deploy, so instances cannot race, but
they apply before the release is known good — every migration must be compatible
with the version before it. See
[`docs/features/deployment.md`](docs/features/deployment.md) for the rest,
including what the free tier's cold starts mean for a customer returning from
Khalti.

`docker-compose.yml` provides local Postgres and Redis. It is not, and never was,
the deployment path.
