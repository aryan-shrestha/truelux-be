# Deployment

Status: Implemented

Last updated: 2026-09-27

---

## Goal

Deploy the TrueLux API to Render as `truelux-api` from `render.yaml`, against
Supabase Postgres and Cloudinary, with nothing else to provision.

---

## Scope

What is included in this implementation?

- `render.yaml`: one native Python web service with its build, start, health check
  and every environment variable
- Production settings for Render's proxy and hostname
- CI: lint, typecheck, tests and a migrations-are-current check

What is explicitly outside the scope?

- Redis (removed, ADR 0014), a task queue, staging, observability beyond Render's
  log stream
- The two Next.js apps, which deploy to Vercel from their own repositories

---

## Context

Supabase (Postgres 15+, required for `NULLS NOT DISTINCT`), Render and Cloudinary
are the only services. ADR 0008 requires every variable, and two tests keep
`render.yaml`, `.env.example` and `base.py` in step.

---

## Implemented

- `render.yaml` — service `truelux-api`, `runtime: python`, free plan, Singapore,
  `healthCheckPath: /health/`. Build: `uv sync --frozen`, `migrate
  --database=direct`, `createcachetable --database=direct`, `seed_staff --deploy`,
  `seed_demo --deploy`, `seed_orders --deploy`, `collectstatic`. Start: gunicorn on
  `$PORT`, 2 workers, 30 s timeout. 37 variables: 17 prompted (`sync: false`),
  `DJANGO_SECRET_KEY` generated, 19 with blueprint values including
  `DJANGO_SETTINGS_MODULE=config.settings.production`, `DJANGO_THROTTLE_AUTH=10/minute`,
  `DJANGO_THROTTLE_ADMIN=2000/hour` and `SEED_DEMO_DATA="true"`.
- `config/settings/production.py` — trusts `X-Forwarded-Proto`, appends
  `RENDER_EXTERNAL_HOSTNAME` to `ALLOWED_HOSTS`, exempts `^health/` from the SSL
  redirect, secure cookies and HSTS.
- `Makefile` `migrate` also runs `createcachetable`, so local matches the build.
- `DATABASE_SCHEMA` — every table lives in this schema on both connections, set as
  the libpq startup parameter `-c search_path=<schema>` in `base.py`. It must be a
  lowercase unquoted identifier. `.env.example` and the test settings use `public`.
- `docker-compose.yml` — local Postgres 16 only, published on host port 5433.
- `.github/workflows/ci.yml` — Postgres 16 service, `make lint`, `make typecheck`,
  `make test`, `makemigrations --check --dry-run`.
- Demo data on deploy (ADR 0015): with `SEED_DEMO_DATA` true, the first build of an
  empty database creates the demo staff login, the catalogue (images uploaded to
  Cloudinary) and the order history; every later build finds the rows and does
  nothing. With it false the three commands print a line and exit 0.
- `tests/test_settings.py` — blueprint/`.env.example`/settings parity, the build
  creates the cache table and then runs the three `--deploy` seeds, the blueprint
  sets `SEED_DEMO_DATA` to `"true"`, the cache is `DatabaseCache`, production
  headers, `DATABASE_SCHEMA` becomes both connections' `search_path`.

---

## Remaining

- **No deploy of TrueLux has been run.** Everything here is configuration verified by
  tests, not observed on Render.
- **Migrations run in the build command**, because the free tier has no
  `preDeployCommand`; each migration must be compatible with the previous release.
- **No staging environment and no error tracking.**
- **Not yet observed that Supavisor honours the `options` startup parameter.** After
  the first deploy with a non-`public` schema, run `SHOW search_path` over both
  aliases with production's env. If the pooler drops it, the fallback is
  `ALTER ROLE <pooler user> SET search_path = <schema>;`.

---

## Decisions

### Decision: the database cache table is built by the build command

**Decision**

`createcachetable --database=direct` runs after `migrate` in the build.

**Reason**

ADR 0014: the throttle counters live in `django_cache`, which no migration creates.
Without it every throttled request fails; `/health/ready/` reports `cache: error`.

### Decision: the build seeds a demo when `SEED_DEMO_DATA` is true

**Decision**

[ADR 0015](../decisions/0015-the-build-seeds-demo-data-when-asked.md). The blueprint
sets `SEED_DEMO_DATA="true"` and the build runs the three seed commands with
`--deploy`. `DEMO_STAFF_EMAIL` and `DEMO_STAFF_PASSWORD` are `sync: false` and
become the admin login of the demo.

**Reason**

The free tier has no shell and no jobs, so the build is the only place a fresh
deploy can get a catalogue and a staff login.

### Decision: the schema is a startup parameter, created by the operator

**Decision**

`DATABASE_SCHEMA` is required (ADR 0008) and passed as `options=-c search_path=<schema>`
on both aliases, with no `public` fallback. Nothing in the app creates the schema:
before the first deploy run `CREATE SCHEMA <schema>;` in the Supabase SQL editor,
and grant `USAGE, CREATE` on it if the connecting role does not own it.

**Reason**

The transaction pooler gives each transaction whichever server connection is free,
so a `SET search_path` on connect would not follow later queries; a startup
parameter is applied to every server connection. `migrate` creates
`django_migrations` before any migration runs, so a migration cannot create the
schema it lives in. Leaving `public` off the path means nothing can land there
silently; the app needs no extension, and `gen_random_uuid` is in `pg_catalog`.

---

## Gotchas

- `DJANGO_CORS_ALLOWED_ORIGINS` may be empty and boots cleanly, but then the
  storefront is blocked by the browser. The admin app calls the API from its server
  (ADR 0012) and needs no CORS entry.
- The free instance sleeps; the first request pays a cold start.
- `/health/` touches nothing; `/health/ready/` checks the database and the cache
  table and is not the platform health check.
- `Missing staticfiles manifest entry` means the build ran without
  `DJANGO_SETTINGS_MODULE=config.settings.production`.
- The region cannot be changed after creation.
- `no schema has been selected to create in` from `migrate` means the schema in
  `DATABASE_SCHEMA` does not exist in that database.
- For a real shop set `SEED_DEMO_DATA` to `"false"` in the dashboard before the
  first deploy. Switching it off later keeps whatever was seeded.
- `DEMO_STAFF_PASSWORD` under 12 characters fails the build while
  `SEED_DEMO_DATA` is true.
- Locally, a Homebrew Postgres on 5432 would shadow the container and is too old
  (14) for `NULLS NOT DISTINCT`; that is why compose uses 5433.

---

## Loading the real catalogue

The client's catalogue is imported from the owner's machine, not by the build
([ADR 0016](../decisions/0016-the-real-catalogue-is-imported-from-a-workbook.md);
full runbook in `catalogue-import.md`):

1. Put production's variables in `.env.production` (gitignored, never committed):
   `DATABASE_URL`, `DATABASE_DIRECT_URL`, `DATABASE_SCHEMA`, the Cloudinary keys and the rest of
   `.env.example`, with `SEED_DEMO_DATA=false`.
2. Set `SEED_DEMO_DATA` to `"false"` in the Render dashboard, so the build does not
   seed demo products into the real shop.
3. `ENV_FILE=.env.production DJANGO_SETTINGS_MODULE=config.settings.production make
   catalogue-import FILE=… IMAGES=… ARGS=--dry-run`, fix what it reports, then run it
   without `--dry-run`.

`ENV_FILE` makes the settings read that file instead of `.env`; a missing file fails
at import.

---

## Data changes

None.

---

## Permissions

Render dashboard access controls who can deploy and read secrets.

---

## Tests

`tests/test_settings.py` — every variable required, secrets never echoed, the
blueprint declares exactly the settings' variables, builds under production settings,
creates the cache table and then seeds, sets `SEED_DEMO_DATA` to `"true"`,
production security headers and Render hostname, `DATABASE_SCHEMA` is validated and
becomes both aliases' `search_path`. The `--deploy` paths are tested
with the commands: `apps/users/tests/test_auth.py`,
`apps/catalog/tests/test_seed_demo.py`, `apps/orders/tests/test_seed_orders.py`.

---

## Files

```text
render.yaml
config/settings/production.py
docker-compose.yml
Makefile
.github/workflows/ci.yml
tests/test_settings.py
```
