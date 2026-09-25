# Deployment

Status: Implemented

Last updated: 2026-09-25

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
  --database=direct`, `createcachetable --database=direct`, `collectstatic`. Start:
  gunicorn on `$PORT`, 2 workers, 30 s timeout. 36 variables: 16 prompted
  (`sync: false`), `DJANGO_SECRET_KEY` generated, 19 with blueprint values including
  `DJANGO_SETTINGS_MODULE=config.settings.production`, `DJANGO_THROTTLE_AUTH=10/minute`
  and `DJANGO_THROTTLE_ADMIN=2000/hour`.
- `config/settings/production.py` — trusts `X-Forwarded-Proto`, appends
  `RENDER_EXTERNAL_HOSTNAME` to `ALLOWED_HOSTS`, exempts `^health/` from the SSL
  redirect, secure cookies and HSTS.
- `Makefile` `migrate` also runs `createcachetable`, so local matches the build.
- `docker-compose.yml` — local Postgres 16 only, published on host port 5433.
- `.github/workflows/ci.yml` — Postgres 16 service, `make lint`, `make typecheck`,
  `make test`, `makemigrations --check --dry-run`.
- `tests/test_settings.py` — blueprint/`.env.example`/settings parity, the build
  creates the cache table, the cache is `DatabaseCache`, production headers.

---

## Remaining

- **No deploy of TrueLux has been run.** Everything here is configuration verified by
  tests, not observed on Render.
- **Migrations run in the build command**, because the free tier has no
  `preDeployCommand`; each migration must be compatible with the previous release.
- **No staging environment and no error tracking.**

---

## Decisions

### Decision: the database cache table is built by the build command

**Decision**

`createcachetable --database=direct` runs after `migrate` in the build.

**Reason**

ADR 0014: the throttle counters live in `django_cache`, which no migration creates.
Without it every throttled request fails; `/health/ready/` reports `cache: error`.

### Decision: the demo staff variables are required in production too

**Decision**

`DEMO_STAFF_EMAIL` and `DEMO_STAFF_PASSWORD` are `sync: false` in the blueprint.

**Reason**

ADR 0008 has no optional variables. `seed_staff` refuses to run without `DEBUG`, so
in production the values are never used; any placeholder works.

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
- Locally, a Homebrew Postgres on 5432 would shadow the container and is too old
  (14) for `NULLS NOT DISTINCT`; that is why compose uses 5433.

---

## Data changes

None.

---

## Permissions

Render dashboard access controls who can deploy and read secrets.

---

## Tests

`tests/test_settings.py` — every variable required, secrets never echoed, the
blueprint declares exactly the settings' variables, builds under production settings
and creates the cache table, production security headers and Render hostname.

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
