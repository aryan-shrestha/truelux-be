# Staff identity

Status: Implemented

Last updated: 2026-09-23

---

## Goal

Give the project a user table, a working URLConf, and the shared API
infrastructure every later feature depends on. Phase 1 has no customer accounts,
so the only identities are staff who sign in to the Django admin.

---

## Scope

Included:

- Custom user model keyed by email, with a `UserManager`
- `apps/core` infrastructure: base models, error envelope, pagination,
  `IsOwnerOrAdmin`, JSON logging with a request id, health endpoints
- Settings split, with `base.py` as the only module that reads the environment
- Tooling: Makefile, ruff, mypy, pytest, pre-commit, CI, and a Dockerfile
  (since deleted — `deployment.md` (#12) dropped the container in favour of a
  native Render service)

Explicitly outside:

- Any `/api/v1/` route. There is no registration, login, or token endpoint.
- Customer accounts, deferred to Phase 2.

---

## Context

`config/urls.py` previously included `apps.users.urls`, which did not exist, so the
URLConf raised on import and nothing in the repository could run. That is why this
feature is first in `docs/features/index.md`.

JWT is configured in `REST_FRAMEWORK` and `SIMPLE_JWT` but is unreachable: nothing
issues a token. Staff authenticate to `/admin/` with session authentication.

---

## Implemented

- `apps/users/models.py` — `User` (UUID pk, email as `USERNAME_FIELD`, no username,
  `first_name`/`last_name`, `is_active`/`is_staff`) and `Profile` (1:1, `display_name`,
  `avatar`). `UserManager.create_user` / `create_superuser` key on email.
- `apps/users/admin.py` — `UserAdmin` with a `Profile` inline. Subclasses
  `django.contrib.auth.admin.UserAdmin` but replaces `fieldsets`, `add_fieldsets`
  and `ordering`, which is what keeps the stock admin from reaching for `username`.
- `apps/users/migrations/0001_initial.py` — both models and the email check constraint.
- `apps/core/models.py` — `TimeStampedModel`, `UUIDModel`.
- `apps/core/exceptions.py` — `DomainError` and `api_exception_handler`, producing one
  envelope for domain errors, DRF errors, `IntegrityError`, and unhandled exceptions.
- `apps/core/logging.py` / `middleware.py` — structlog configured to render both its
  own events and plain stdlib records as one JSON line each, `get_logger`, and
  `RequestIDMiddleware` binding the request id into context variables and setting the
  `X-Request-ID` header. Also `RedactUUIDs`, a filter attached to `django.request`
  only: Django writes the request path on a 5xx, and an order's `access_token` is a
  path segment. The application's own lines log identifiers deliberately and go
  through `apps`, so they are untouched.
- `apps/core/views.py` — `/health/` and `/health/ready/`.
- `apps/core/permissions.py` — `IsOwnerOrAdmin`. No view uses it: ADR 0003 gave
  Phase 1 no customer accounts and no row with a `user` foreign key. It is
  Phase 2 scaffolding, and `architecture.md` marks the section describing it
  superseded.
- `apps/core/pagination.py` — `DefaultLimitOffsetPagination`, limit ceiling 100.
- `apps/core/throttling.py` — `ResilientAnonRateThrottle` / `ResilientUserRateThrottle`,
  which fall back to a per-process cache when Redis is unreachable.
- `config/settings/` — `base.py` reads every environment variable; `local`, `test`
  and `production` only override.

---

## Remaining

- `Profile` has no writer. Nothing creates one on user creation, so a user may exist
  without a profile; staff add one through the admin inline. It was retained on
  request for a later phase, and overlaps `User.first_name`/`last_name`, which is
  what `docs/architecture.md` currently documents. Resolve when a profile consumer
  exists.
- The `avatar` upload path has never been exercised against Cloudinary. Local and test
  settings both use `FileSystemStorage`, per `media-storage.md`.

---

## Decisions

### Decision: health endpoints opt out of API versioning

**Decision** — `LivenessView` and `ReadinessView` set `versioning_class = None`.

**Reason** — `NamespaceVersioning` reads the resolved URL namespace and raises
`NotFound` for anything outside `ALLOWED_VERSIONS`. `apps/core/urls.py` declares
`app_name = "health"`, so both probes returned 404 until versioning was disabled.

**Consequence** — Health endpoints are unversioned infrastructure. Any future
route mounted outside `/api/v1/` that uses DRF must do the same.

### Decision: the user admin stays a naive ModelAdmin

**Decision** — `UserAdmin` uses the default write path; nothing is routed through a
service.

**Reason** — ADR 0002 splits admin writes by business consequence: a write is routed
only where a service exists because changing the field should cause something else to
happen. Editing an email or an active flag in Phase 1 causes nothing else, and
`apps/users` has no service layer.

**Consequence** — If a user write ever gains a consequence (a verification email, a
deactivation cascade), it must move to an action calling a service, per ADR 0002.

### Decision: throttling fails open when Redis is unreachable

**Decision** — `apps/core/throttling.py` wraps DRF's throttles and allows the request
if the cache backend raises.

**Reason** — DRF's stock throttles let the cache error propagate. Because the throttle
runs before the view on every endpoint, a Redis outage turned *every* request into a
500, including `/api/schema/`. `docs/architecture.md` requires that a Redis outage
"never change a response's correctness — only its latency".

**Consequence** — Rate limiting silently disappears while Redis is down, logged at
WARNING as `throttle.backend_unavailable`. That is the accepted trade: the
known-limitations section already treats throttling as only as reliable as Redis,
and availability is worth more than a rate limit here.

### Decision: error codes are mapped, not taken from DRF

**Decision** — `_DOCUMENTED_CODES` in `apps/core/exceptions.py` maps
`ValidationError` to `validation_error` and `NotAuthenticated` to
`authentication_failed`.

**Reason** — DRF's `default_code` for those is `invalid` and `not_authenticated`,
which contradicts the error table in `docs/architecture.md`. Codes are a public API
that clients branch on, so the documented spelling wins.

**Consequence** — Any new DRF exception whose `default_code` differs from the
documented table must be added to that tuple.

### Decision: the readiness probe returns no exception text

**Decision** — Each check returns the literal `"ok"` or `"error"`; the exception goes
to the log.

**Reason** — The endpoint is unauthenticated and unthrottled. A psycopg or Redis
error string can contain the host, database name, or credentials.

---

## Gotchas

- `DISABLE_SERVER_SIDE_CURSORS` is a key **inside** `DATABASES["default"]`. At module
  level Django ignores it silently, and a pooled connection then produces
  `InvalidCursorName` errors that never reproduce locally.
- `DATABASE_DIRECT_URL` is required and has no fallback. It previously defaulted to
  `DATABASE_URL`, which meant an unset value silently migrated over the pooler --
  a failure that only appears in production.
- Migrations run over the `direct` database alias (`DATABASE_DIRECT_URL`); the
  pooler cannot hold the locks they take. The alias carries
  `TEST = {"MIRROR": "default"}` so the test runner does not build a second database
  for the same server. `make migrate` passes `--database=direct`.
- `user.profile` raises `RelatedObjectDoesNotExist` when no profile row exists, which
  is the common case: nothing creates one automatically.
- An inbound `X-Request-ID` is echoed into the response and every log line, so
  `RequestIDMiddleware` accepts it only if it matches `[A-Za-z0-9._-]{1,64}` and
  generates a fresh id otherwise.
- `SIMPLE_JWT` lifetimes must be `timedelta`, not integers.
- factory_boy types `DjangoModelFactory.__call__` as returning the factory, not the
  model, so `attr-defined` is disabled for test modules in `pyproject.toml`.
- `mypy` rejects `# type: ignore[code] - reason`. The reason must follow a second `#`.
  `convention.md` previously documented the unparseable form.
- Settings modules are the one place wildcard imports are allowed; `F403`/`F405` are
  suppressed for `config/settings/*` in `pyproject.toml`, not inline.

---

## API

No `/api/v1/` routes. Infrastructure endpoints only:

```text
GET /health/        → 200 {"status": "ok"}
GET /health/ready/  → 200 {"status": "ready",     "checks": {"database": "ok", "cache": "ok"}}
                    → 503 {"status": "not_ready", "checks": {"database": "ok", "cache": "error"}}
```

Both are unauthenticated and unthrottled. Every response carries `X-Request-ID`.

---

## Data changes

`0001_initial` creates:

- `users` — UUID pk, `email` unique, `first_name`, `last_name`, `is_active`,
  `is_staff`, `created_at`/`updated_at`, plus the `PermissionsMixin` relations.
  `CheckConstraint user_email_not_empty` rejects an empty email.
- `user_profiles` — UUID pk, `user` one-to-one (`CASCADE`), `display_name`, `avatar`,
  `created_at`/`updated_at`.

No indexes beyond the implicit ones: nothing queries these tables yet, and
`docs/convention.md` forbids speculative indexes. `created_at` carries `db_index`
from `TimeStampedModel`.

---

## Permissions

`IsAuthenticated` is the project-wide default, so any future endpoint is private
unless it opts out. The health endpoints opt out with `AllowAny`. `IsOwnerOrAdmin`
exists in `apps/core` and admits staff, but no endpoint uses it yet.

---

## Tests

- `apps/users/tests/test_admin.py` — the changelist, add and change pages render, and
  creating a user through the admin hashes the password and creates the profile inline.
  This is the concrete check that the custom user model does not trip the stock
  `UserAdmin`'s `username` assumption recorded in `merchant-admin.md`.
- `apps/users/tests/test_models.py` — email normalisation, password hashing, manager
  guard rails, the unique and check constraints, UUID assigned before insert,
  `updated_at` advancing under `freeze_time`, profile cascade delete.
- `apps/core/tests/test_exceptions.py` — every failure class produces the same
  envelope; 422/400/404/403/409/500 mapping; no database detail or connection string
  reaches the response body.
- `apps/core/tests/test_health.py` — both probes are public, liveness issues zero
  queries, readiness returns 503 with no exception text when either dependency fails,
  and an inbound `X-Request-ID` is preserved.
- `apps/core/tests/test_permissions.py` — owner allowed, other user denied, staff allowed.
- `apps/core/tests/test_throttling.py` — a shared-backend outage still enforces the
  limit per process, counts into the dedicated fallback alias, restores the shared
  cache afterwards, and does not turn a request into a 500.
- `apps/core/tests/test_logging.py` — one JSON object per line, keyword context hoisted
  to top-level keys, the bound request id stamped, the key still present outside a
  request, exceptions rendered, plain stdlib records rendered the same way, and a
  UUID in a `django.request` message redacted while an ordinary slug path is left
  alone.
- `tests/test_settings.py` — each required variable raises at import when absent;
  production sets the security headers and renders JSON only; the pooler constraints
  are applied, `ATOMIC_REQUESTS` among them, because that setting silently decides
  whether the Khalti call happens inside a transaction; and `STOREFRONT_URL` must be
  https away from localhost.

---

## Files

```text
apps/core/
├── exceptions.py
├── logging.py
├── middleware.py
├── models.py
├── logging.py
├── middleware.py
├── pagination.py
├── permissions.py
├── throttling.py
├── urls.py
├── views.py
└── tests/

apps/users/
├── admin.py
├── models.py
├── migrations/0001_initial.py
└── tests/

config/settings/{base,local,test,production}.py
```

---

## Future context

The first `/api/v1/` route must add its include to `api_v1_patterns` in
`config/urls.py`, which is currently an empty list kept so the `v1` namespace and
`NamespaceVersioning` stay wired.

ADR 0003 notes the order-number fallback will need its own `ScopedRateThrottle`. It
should mix in `PerProcessFallbackThrottleMixin`, or it reintroduces the
Redis-outage-500 that mixin exists to prevent.

`apps/users` has no `services.py` or `selectors.py`. They were written and then
removed when the API surface was cut: with no callers they were dead code. Recreate
them when something writes to or reads the user table outside the admin.
