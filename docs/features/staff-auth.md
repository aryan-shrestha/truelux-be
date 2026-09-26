# Staff auth

Status: Implemented

Last updated: 2026-09-26

---

## Goal

Let staff sign in to the TrueLux admin app (`admin.truelux.com`), a separate Next.js
application, with tokens it can hold server-side.

---

## Scope

What is included in this implementation?

- `POST /api/v1/auth/token/`: email and password in, access and refresh token out,
  **staff only**
- `POST /api/v1/auth/token/refresh/`: rotation with blacklist-after-rotation
- `POST /api/v1/auth/logout/`: blacklists the refresh token
- `GET /api/v1/auth/me/`: the signed-in staff user
- A dedicated `auth` throttle scope on the token endpoints
- `make seed-staff`, which creates the demo staff user from `DEMO_STAFF_EMAIL` and
  `DEMO_STAFF_PASSWORD` (DEBUG only), and `seed_staff --deploy`, which the Render
  build runs (ADR 0015)

What is explicitly outside the scope?

- Customer accounts, registration and password reset
- Roles finer than `is_staff`. Every staff user can do everything in the admin app.
- MFA

---

## Context

`SIMPLE_JWT` is already configured in `config/settings/base.py`, with
`ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION`, but nothing issues tokens.
`rest_framework_simplejwt.token_blacklist` must be in `INSTALLED_APPS` for the
blacklist to work.
[ADR 0012](../decisions/0012-the-admin-app-authenticates-with-jwt-held-server-side.md)
explains why the admin app uses JWT and where the tokens live.

The admin app calls the API **from its server only**, so these endpoints need no
CORS entry for the admin origin.

---

## Planned

- `apps/users/serializers.py`: a subclass of `TokenObtainPairSerializer` that rejects
  `is_active=False` and `is_staff=False` users with **the same** 401
  `authentication_failed` as a wrong password. The API does not reveal that an
  account exists but lacks staff rights.
- `apps/users/views.py`, `apps/users/urls.py` mounted at `/api/v1/auth/`.
- `TokenRefreshView` also rejects a refresh token whose user has since lost
  `is_staff` or `is_active`.
- `ScopedRateThrottle` with scope `auth`, rate from `DJANGO_THROTTLE_AUTH`
  (`10/minute` in the blueprint).
- `DEFAULT_AUTHENTICATION_CLASSES` includes `JWTAuthentication`.
  `SessionAuthentication` stays for the Django admin only.

---

## Implemented

- `apps/users/authentication.py` — `is_active_staff`, installed as SimpleJWT's
  `USER_AUTHENTICATION_RULE`. SimpleJWT applies the rule when it issues a pair and
  again on every refresh, so it covers both the staff-only login and a de-staffed
  refresh token.
- `apps/users/views.py` — `StaffTokenObtainView` and `StaffTokenRefreshView`
  (SimpleJWT's views with `ScopedRateThrottle`, scope `auth`), `LogoutView` and
  `MeView` (`JWTAuthentication` only, `IsAuthenticated` + `IsAdminUser`).
- `apps/users/services.py` — `revoke_refresh_token` blacklists a refresh token
  after checking it belongs to the caller.
- `apps/users/urls.py` — mounted under `/api/v1/auth/`.
- `apps/users/management/commands/seed_staff.py` and `make seed-staff` — create or
  reset `DEMO_STAFF_EMAIL` as an active staff user named Asha Rai, with
  `DEMO_STAFF_PASSWORD`. Refuses outside `DEBUG`. With `--deploy` it runs outside
  `DEBUG` but only while `SEED_DEMO_DATA` is true (otherwise a no-op), creates the
  user only if no user has that email (case-insensitive), never resets a password,
  and rejects a `DEMO_STAFF_PASSWORD` under 12 characters.
- `config/settings/base.py` — `auth` (`DJANGO_THROTTLE_AUTH`) and `admin`
  (`DJANGO_THROTTLE_ADMIN`) throttle scopes; `DEMO_STAFF_EMAIL` and
  `DEMO_STAFF_PASSWORD`, required like every variable (ADR 0008), in `.env.example`
  and `render.yaml` (`sync: false`). `DEMO_STAFF_PASSWORD` is on `NEVER_ECHOED`.
- `rest_framework_simplejwt.token_blacklist` was already installed; its migrations
  run with `make migrate`.

---

## Remaining

None.

---

## Decisions

### Decision: the staff rule lives in `USER_AUTHENTICATION_RULE`, not a serializer

**Decision**

The planned `TokenObtainPairSerializer` subclass was not written. The rule function
is configured once in `SIMPLE_JWT`.

**Reason**

SimpleJWT already raises its `no_active_account` 401 when the rule fails, for login
and refresh alike, so a subclass would duplicate that and still need a second one
for refresh.

**Consequence**

Wrong password, unknown email, inactive and non-staff all produce one body:
`401 authentication_failed`, "No active account found with the given credentials".

### Decision: a bad refresh token on logout is a 422, not a 401

**Decision**

`POST /auth/logout/` with a malformed, expired, revoked or someone else's refresh
token returns `422 invalid_refresh_token`.

**Reason**

The request itself is authenticated by the access token; only the body is wrong.
The service raises a `DomainError`, as every service here does.

---

## Gotchas

- `JWTAuthentication` itself does not apply the rule: a non-staff user's access
  token still authenticates and gets `403` from `IsAdminUser`. Only SimpleJWT's
  obtain and refresh consult `is_active_staff`.
- The Django admin session is ignored by these endpoints (and by `/api/v1/admin/`):
  the global authentication class is JWT only.
- A refresh token whose user row has been deleted makes SimpleJWT's refresh raise
  `User.DoesNotExist`, which the handler reports as `404 not_found`.
- The access token lives 15 minutes and the refresh token 7 days
  (`JWT_ACCESS_TOKEN_LIFETIME_MINUTES`, `JWT_REFRESH_TOKEN_LIFETIME_DAYS`).
- `DJANGO_SECRET_KEY` signs the tokens; PyJWT warns below 32 bytes.
- On a deploy, changing `DEMO_STAFF_PASSWORD` does nothing once the user exists:
  `--deploy` never resets it. Change the password from the Django admin instead.

---

## API

### `POST /api/v1/auth/token/`

```json
{ "email": "staff@truelux.com", "password": "..." }
```

`200`:

```json
{ "access": "<jwt>", "refresh": "<jwt>" }
```

`401 authentication_failed` for a wrong password, an unknown email, an inactive
user or a non-staff user. All four return the same body.

### `POST /api/v1/auth/token/refresh/`

`{ "refresh": "<jwt>" }` → `200 { "access": "<jwt>", "refresh": "<jwt>" }`. The old
refresh token is blacklisted. A blacklisted, expired or de-staffed refresh token
returns `401 authentication_failed`.

### `POST /api/v1/auth/logout/`

Bearer access token required. `{ "refresh": "<jwt>" }` → `204`. Blacklists the
refresh token. A refresh token that is invalid, revoked or belongs to another user
returns `422 invalid_refresh_token`.

### `GET /api/v1/auth/me/`

Bearer access token, staff required.

```json
{ "id": "uuid", "email": "staff@truelux.com", "first_name": "Asha", "last_name": "Rai" }
```

---

## Data changes

The SimpleJWT `token_blacklist` migrations. No model changes.

---

## Permissions

The token and refresh endpoints are public but throttled. `me` and `logout` require
`IsAuthenticated` + `IsAdminUser`.

---

## Tests

`apps/users/tests/test_auth.py`:

- Staff login returns `access` and `refresh`; wrong password, unknown email,
  inactive and non-staff return byte-identical 401 bodies.
- Refresh rotates, and reusing the old token is 401; refresh fails after the user
  loses `is_staff`.
- Logout blacklists the refresh token; another user's token is 422; logout needs a
  token.
- `me` returns the user, is 401 without a token, 403 for a non-staff token, and
  401 with only a Django admin session.
- The `auth` throttle returns 429.
- `seed_staff` is idempotent, produces a login that works, and refuses outside DEBUG.
  `--deploy` creates a working login outside DEBUG, is a no-op while
  `SEED_DEMO_DATA` is false, leaves an existing user's password alone, and rejects a
  password under 12 characters.

---

## Files

```text
apps/users/
├── authentication.py
├── exceptions.py
├── serializers.py
├── services.py
├── urls.py
├── views.py
├── management/commands/seed_staff.py
└── tests/test_auth.py
config/settings/base.py
```
