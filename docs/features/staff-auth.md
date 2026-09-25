# Staff auth

Status: Planned

Last updated: 2026-09-25

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
  `DEMO_STAFF_PASSWORD` (DEBUG only)

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
refresh token.

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

To be written:

- Staff login succeeds; non-staff, inactive, unknown email and wrong password all
  return byte-identical 401 bodies.
- Refresh rotates the token and blacklists the old one; reusing the old token is 401.
- Refresh fails after the user loses `is_staff`.
- Logout blacklists the refresh token.
- `me` requires a token; a non-staff token is 403.
- The `auth` throttle returns 429 `throttled`.
