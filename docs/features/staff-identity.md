# Staff identity

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Give the project its user table and the shared API infrastructure every feature
depends on. The only identities are staff: there are no customer accounts. How staff
sign in to the API is `staff-auth.md`.

---

## Scope

Included:

- Custom user model keyed by email, with a `UserManager`
- `apps/core` infrastructure: base models, error envelope, pagination,
  `IsOwnerOrAdmin`, JSON logging with a request id, health endpoints
- Settings split, with `base.py` as the only module that reads the environment
- Tooling: Makefile, ruff, mypy, pytest, pre-commit, CI

Explicitly outside:

- Customer accounts and registration

---

## Implemented

- `apps/users/models.py` — `User` (UUID pk, email as `USERNAME_FIELD`,
  `first_name`/`last_name`, `is_active`/`is_staff`) and `Profile` (1:1,
  `display_name`, `avatar`).
- `apps/users/admin.py` — `UserAdmin` with a `Profile` inline, at `/django-admin/`.
- `apps/core/models.py` — `TimeStampedModel`, `UUIDModel`.
- `apps/core/exceptions.py` — `DomainError` and `api_exception_handler` (one envelope
  for domain errors, DRF errors, `IntegrityError`/`ProtectedError`, Django
  `ValidationError`, `ObjectDoesNotExist` and unhandled exceptions).
- `apps/core/logging.py`, `middleware.py` — structlog JSON lines, `get_logger`,
  `RequestIDMiddleware`, and `RedactUUIDs` on `django.request` so an
  `access_token` in a 5xx path is never logged.
- `apps/core/views.py` — `/health/` (touches nothing) and `/health/ready/` (database
  and the `django_cache` table; 503 without exception text).
- `apps/core/permissions.py` — `IsOwnerOrAdmin`, unused (ADR 0003).
- `apps/core/pagination.py` — `DefaultLimitOffsetPagination`, 25 per page, max 100.
- Throttling uses DRF's own `AnonRateThrottle`, `UserRateThrottle` and
  `ScopedRateThrottle` over the database cache (ADR 0014); the fork's per-process
  Redis fallback (`apps/core/throttling.py`) is deleted.

---

## Remaining

- `Profile` has no writer outside the admin inline, and no consumer.

---

## Decisions

### Decision: health endpoints opt out of API versioning

**Decision**

`versioning_class = None` on both health views.

**Reason**

They sit outside `/api/v1/`, and `NamespaceVersioning` would reject their namespace.

### Decision: error codes are mapped, not taken from DRF

**Decision**

`_PUBLISHED_CODES` in `apps/core/exceptions.py` names every public code.

**Reason**

A DRF upgrade must not silently rename the API's error codes.

### Decision: the readiness probe returns no exception text

**Reason**

It is unauthenticated; a connection error can carry credentials.

---

## Gotchas

- Never change `AUTH_USER_MODEL`.
- The global DRF authentication class is JWT only; the Django admin's session does
  not authenticate API requests.
- Tests use local-memory cache; `apps/core/tests/test_throttling.py` proves the
  database-backed throttle.

---

## API

`GET /health/` → `{"status": "ok"}`. `GET /health/ready/` →
`{"status": "ready", "checks": {"database": "ok", "cache": "ok"}}` or 503 with
`"not_ready"`.

---

## Data changes

`users`, `user_profiles` (fresh `0001_initial`), plus SimpleJWT's
`token_blacklist` tables and the `django_cache` table.

---

## Permissions

Health endpoints are public. Everything else is in the feature docs.

---

## Tests

`apps/core/tests/` (exception envelope, logging, health, pagination, permissions,
schema generation with `--fail-on-warn`, the database-cache throttle),
`apps/users/tests/` (model, admin, the `/django-admin/` mount), `tests/` (settings,
storage).

---

## Files

```text
apps/core/
apps/users/{models,admin}.py
config/settings/
```
