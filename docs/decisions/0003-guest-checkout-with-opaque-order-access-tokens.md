# ADR 0003: Guest checkout, with opaque order access tokens

Status: Accepted

Date: 2026-09-20

Supersedes: None

---

## Context

The brand currently sells through Instagram. Its customers arrive from a link in a
bio, have never heard of the store's website, and are deciding whether to buy in the
next ninety seconds. Requiring them to create an account, verify an email, and
remember a password before they can pay is the single largest drop-off available to
introduce.

`architecture.md` assumes the opposite. `IsAuthenticated` is the project-wide
default, object ownership is defined as "a row with a `user` foreign key is
readable and writable only by that user", and `apps/users` was scaffolded with
registration, password change, and JWT logout services.

If there are no accounts, then an order has no owner, and the ownership rule that
the entire authorization model rests on does not apply to the most sensitive table
in the system. Something has to replace it, because an order contains a customer's
name, phone number, and home address.

## Decision

**Phase 1 has no customer accounts.** Checkout collects an email, a phone number,
and a shipping address, and creates an order. There is no registration endpoint, no
login endpoint, and no token endpoint.

**`Order` has no `user` foreign key at all** — not a nullable one.

**Order access is by opaque token.** Every order carries an `access_token`
(`UUIDField`, `default=uuid4`, unique, never reused). The confirmation email
contains a link embedding it, and `GET /api/v1/orders/<access_token>/` returns the
order. The token *is* the credential.

**Order number plus email is a throttled fallback**, for the customer who deleted
the email. It is a separate endpoint with its own scoped throttle, and it returns
the same 404 whether the order number does not exist or the email does not match.

`apps/users` keeps the `User` model and its manager, because `AUTH_USER_MODEL`
points at it and `django.contrib.admin` requires it. Staff authenticate to the
admin with session authentication.

## Reason

Conversion is the whole point of building the site. A brand moving off Instagram is
trying to capture people who were already going to buy; an account wall loses a
share of them for a benefit — order history — that a first-phase store does not
need to provide.

The token design follows from what actually protects the data. An order number is
sequential or near-sequential, so it is enumerable; an email address is guessable
for anyone who knows the customer. Neither is a credential. A 128-bit random token
delivered to the address that placed the order is one, and it costs a column.

Omitting the `user` foreign key entirely, rather than making it nullable, is the
smaller lie. A nullable FK invites selectors with two code paths — one for the
logged-in case that does not exist yet — and invites a future reader to assume the
authenticated path is live. Adding a nullable column in Phase 2 is one migration.

## Alternatives considered

### Require an account to check out

Why it was not chosen: it makes `Order.user` non-null, makes order lookup a
one-line selector, and reuses `IsOwnerOrAdmin` unchanged — genuinely the cleaner
engineering. It was rejected on product grounds, not technical ones. The auth
surface it needs is roughly a week of work that buys a feature (order history) that
nobody has asked for, and it taxes every sale to pay for it.

### Guest checkout with lookup by order number and email only

Why it was not chosen: it is an enumeration surface. An attacker who guesses an
order number and knows a customer's email — or who tries a list of both — reads a
home address. Rate limiting makes this slower, not impossible.

### Guest checkout with a short numeric PIN in the email

Why it was not chosen: a six-digit PIN is brute-forceable in a way a UUID is not,
and it buys only marginally better ergonomics over a link the customer clicks.

### Magic-link accounts (passwordless)

Why it was not chosen: it is an authentication system with extra steps — token
issuance, expiry, replay protection — for a phase that has decided it does not need
authentication. It is a strong Phase 2 candidate precisely because it preserves the
no-password property while adding history.

## Consequences

### Positive

- The shortest possible path from an Instagram link to a completed order.
- No password storage, no password reset flow, no account enumeration on
  registration, no session fixation surface. The entire authentication attack
  surface for customers is absent because the feature is absent.
- Order selectors have exactly one code path.

### Negative

- **A customer who loses the confirmation email and forgets the order number cannot
  reach their order.** The merchant must look it up in the admin. This is a real
  support cost and it is accepted.
- No order history, no saved addresses, no "reorder". Every purchase is standalone.
- The access token is a bearer credential in a URL. It will end up in browser
  history and in any analytics that log full paths. Referrer leakage must be
  controlled, and the order page must not load third-party scripts.
- **Every Phase 1 API endpoint opts out of the global `IsAuthenticated` default.**
  The public surface is the whole surface. This makes the per-endpoint permission
  review in `catalog-browsing.md` and `payments.md` load-bearing rather than
  ceremonial.
- `SIMPLE_JWT` and `rest_framework_simplejwt.token_blacklist` are configured but
  unreachable, because nothing issues a token. They stay installed — removing
  `token_blacklist` from `INSTALLED_APPS` and restoring it in Phase 2 causes
  migration churn for no gain — but nobody should read their presence as evidence
  that the API is authenticated.
- **The Khalti return hands the token out in a `Location` header.**
  `apps/payments/views.py` answers a successful verification with a 302 to
  `{STOREFRONT_URL}/orders/<access_token>`, so the credential travels in a response
  header that proxies, CDNs and browser tooling routinely log — and a leaked `pidx`
  becomes a leaked token with one unauthenticated GET. This is accepted for Phase 1
  rather than overlooked: the alternative is landing the customer on a page that
  cannot show them the order they just paid for, and asking them to go and find
  their email. Revisit with the storefront, since any fix changes what the other
  repository receives.

### Constraints introduced

- `Order.access_token` is unique, indexed, and never logged. It is a credential and
  falls under `convention.md`'s never-log list alongside tokens and passwords. The
  application never logs it, and `django.request` — which writes the request path
  on a 5xx, and the token is a path segment — carries a redacting filter
  (`apps.core.logging.RedactUUIDs`). Gunicorn's access log is not covered, and is
  the remaining place a token can surface.
- `STOREFRONT_URL` must be `https` away from localhost, enforced at boot. The
  confirmation email links to `{STOREFRONT_URL}/orders/<access_token>`, and over
  `http` that link is a bearer credential in clear text.
- The order detail endpoint must return 404, never 403, for a wrong token, and the
  order-number fallback must return an identical 404 for "no such order" and "email
  does not match". A distinguishable response is an oracle.
- The order-number fallback needs its own `ScopedRateThrottle` scope. The global
  `anon` rate does not protect it adequately.
- Order confirmation emails must render the token link over HTTPS only.

## Implementation

```text
apps/orders/models.py      Order.access_token; no user FK
apps/orders/selectors.py   get_order_by_access_token, get_order_by_number_and_email
apps/orders/views.py       AllowAny, scoped throttle on the fallback
apps/users/                User model, manager and Profile; no API surface
config/urls.py             does not include apps.users.urls
docs/features/orders.md
docs/features/staff-identity.md
```

## Future reconsideration

Revisit in Phase 2, when customer accounts are added. The migration path is
additive: add a nullable `Order.user`, backfill nothing, and let new authenticated
orders populate it while token access keeps working for old ones. The access token
should survive the transition rather than be removed — it is what makes the
confirmation email link work regardless of login state.

Revisit sooner if support load from customers who cannot find their order becomes
material. The cheapest fix is a resend-confirmation endpoint keyed on email, which
leaks nothing because it delivers only to the address already on the order.
