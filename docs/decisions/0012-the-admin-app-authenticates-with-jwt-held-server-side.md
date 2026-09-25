# ADR 0012: The admin app authenticates with JWT held server-side

Status: Accepted

Date: 2026-09-25

Supersedes: None

---

## Context

The merchant's back-office is a separate Next.js app on `admin.truelux.com`. The
API is on `api.truelux.com`. Before custom domains exist, the demo runs on
`*.vercel.app` and `*.onrender.com`, which are different sites, so cookies from the
API cannot be relied on.

---

## Decision

The API issues SimpleJWT access and refresh tokens to staff only
(`staff-auth.md`). The admin app's **server** obtains them, keeps them in httpOnly,
Secure, SameSite=Lax cookies on its own origin, and sends `Authorization: Bearer`
on every API call it makes from server components and server actions. The browser
never calls the API's admin routes and never sees a token.

---

## Reason

It works on any pair of domains, including preview URLs. There is no CSRF surface
on the API, because it has no cookie auth for the admin, and no CORS entry for the
admin origin. Refresh rotation with a blacklist limits the life of a stolen refresh
token.

---

## Alternatives considered

### A Django session cookie on `.truelux.com`

Why it was not chosen: it only works once the custom domain is live, and it needs CSRF on
every admin write.

### Tokens in browser storage

Why it was not chosen: a token in browser storage can be read by any XSS.

---

## Consequences

### Positive

- It is domain-agnostic, and the API stays stateless for the admin.

### Negative

- Every admin read is a server-side round trip. Acceptable for a back-office.

### Constraints introduced

- Admin routes accept only `JWTAuthentication`.

---

## Implementation

```text
apps/users/views.py
apps/backoffice/views.py
docs/features/staff-auth.md
```
