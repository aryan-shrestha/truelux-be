# ADR 0020: The admin app keeps JWT in browser storage

Status: Accepted

Date: 2026-10-11

Supersedes: [ADR 0012](0012-the-admin-app-authenticates-with-jwt-held-server-side.md)

---

## Context

ADR 0012 kept the staff tokens on the Next.js admin app's server, in httpOnly
cookies, and had that server proxy every API call. The admin app is being rewritten
as a client-only React app. There is no server left to hold the tokens or to proxy,
and keeping one only for that is the complexity the rewrite removes.

---

## Decision

The admin app's browser code calls `/api/v1/auth/*` and `/api/v1/admin/*` directly.
It keeps the SimpleJWT access and refresh tokens in `localStorage` and sends
`Authorization: Bearer <access>` on every call. The API is unchanged: it already
returns both tokens in the JSON body and reads only the `Authorization` header.

The admin app's origin is listed in `DJANGO_CORS_ALLOWED_ORIGINS`, next to the
storefront's.

---

## Reason

It drops the server-side cookie and proxy layer. It still works on any pair of
domains, because header auth needs neither shared cookies nor CSRF.

---

## Alternatives considered

### Keep a server-side proxy (ADR 0012)

Why it was not chosen: it needs a server runtime that the React admin app no longer
has.

### An httpOnly refresh cookie set by the API

Why it was not chosen: the cookie only reaches the API when the admin app and the
API share a site, which the `*.vercel.app` / `*.onrender.com` demo does not. It also
adds a CSRF surface to the refresh endpoint. ADR 0012 rejected session cookies for
the same reasons.

---

## Consequences

### Positive

- The admin app is a static client with no server of its own.
- The API stays stateless for the admin, and it still has no cookie auth or CSRF
  surface.

### Negative

- An XSS on the admin origin can read both tokens. A stolen refresh token is not
  bounded by `JWT_REFRESH_TOKEN_LIFETIME_DAYS` (7): every rotation issues a token
  with a fresh lifetime, so an attacker who keeps refreshing keeps access. Rotation
  blacklists the old token, so whichever of the attacker and the real user refreshes
  second gets a 401, and that 401 is the only signal of theft. The real user's logout
  revokes only their own token. The attacker's chain ends only when the user loses
  `is_active` or `is_staff` (checked on every refresh) or `DJANGO_SECRET_KEY`
  changes. A password change does not revoke tokens.
- An access token cannot be revoked. A stolen one works until it expires, at most
  `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` (15).

### Constraints introduced

- Every environment that runs the admin app must list its origin in
  `DJANGO_CORS_ALLOWED_ORIGINS`. Without it the browser blocks the admin app, and
  nothing appears in the API's logs.
- Admin routes still accept only `JWTAuthentication`.

---

## Implementation

```text
config/settings/base.py          CORS_ALLOWED_ORIGINS from DJANGO_CORS_ALLOWED_ORIGINS
apps/users/views.py
apps/users/tests/test_auth.py    test_a_cross_origin_browser_may_send_a_bearer_token
docs/features/staff-auth.md
```

---

## Future reconsideration

Revisit this if the admin app gets a server runtime again, or if the API and admin
app move under one registrable domain, which would make an httpOnly refresh cookie
practical.
