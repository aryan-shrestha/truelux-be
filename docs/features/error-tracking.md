# Error tracking

Status: Implemented

Last updated: 2026-11-05

---

## Goal

Learn about an error on either server when it happens, not when a customer
complains, without sending customer data to a third party
([ADR 0023](../decisions/0023-errors-are-reported-to-sentry-without-customer-data.md)).

---

## Scope

What is included in this implementation?

- Sentry error reporting from `config.settings.production`, on when `SENTRY_DSN` is set
- Unhandled exceptions and every `ERROR` log line, including `email.send_failed`
- No user identity, cookies, request bodies, query parameters, SQL parameters or
  frame variables, and access tokens redacted from the URL and headers

What is explicitly outside the scope?

- Performance tracing, profiling, session replay, Sentry Logs
- Uptime monitoring, which is an external monitor on the health endpoints
- Shipping logs off the host

---

## Context

`apps/core/logging.py` already redacts UUIDs from `django.request` log lines
(`RedactUUIDs`), because the order page's URL carries the access_token (ADR 0003).
`convention.md` lists what is never logged. Both cPanel apps run
`config.settings.production` (ADR 0022).

---

## Implemented

- `config/settings/base.py` reads `SENTRY_DSN` (may be empty) and
  `SENTRY_ENVIRONMENT` (required).
- `config/settings/production.py` calls `sentry_sdk.init` when `SENTRY_DSN` is
  non-empty, with `environment`, a `data_collection` that turns off user info,
  cookies, HTTP bodies, URL query parameters, SQL parameters and stack-frame
  variables and filters client-IP headers, and `before_send=scrub_sentry_event`.
- `apps/core/logging.py` `scrub_sentry_event` replaces UUIDs in the event's request
  URL and header values with `<redacted>`.
- `.env.example` (`SENTRY_DSN=`, `SENTRY_ENVIRONMENT=local`), the test settings
  (`""`, `test`) and `render.yaml` declare both.

Verified on 2026-11-05 by sending failing requests through Django's WSGI handler
with a capturing transport: events carried method, URL, route and headers, with the
access_token redacted from the URL and `Referer`, `X-Forwarded-For`, `X-Real-Ip` and
`Cf-Connecting-Ip` filtered, and no request body, email, query string, cookie value or
frame variable. Without `scrub_sentry_event` the token was
present in both.

---

## Remaining

- **Not yet seen on the servers.** Each app needs `SENTRY_DSN` and
  `SENTRY_ENVIRONMENT` in its `.env`, then a restart; see `deployment.md`.
- Alert rules (who is notified, for which environment) are configured in Sentry, not
  here.

---

## Decisions

### Decision: production settings only

**Decision**

`sentry_sdk.init` lives in `production.py`, behind a non-empty `SENTRY_DSN`.

**Reason**

Every deployed app runs production settings, and nothing else should report: a
laptop's or CI's errors are not incidents.

### Decision: collection off by category, plus a scrubber for the token

**Decision**

`data_collection` switches whole categories off; `scrub_sentry_event` handles the one
credential the SDK has no category for, a UUID in the path.

**Reason**

A new endpoint with new customer fields is covered without touching this code.

---

## Gotchas

- Django's test client bypasses the WSGI layer, where Sentry records the URL, method
  and headers, so an event captured through it shows almost no request data. Check
  what an event carries through `get_wsgi_application()`, as the verification above
  did.
- **Passing `data_collection` drops the SDK's client-IP header terms.** Without it,
  `send_default_pii=False` filters headers matching `forwarded`, `-ip`, `remote-`,
  `via` and `-user`; with it, only the base denylist applies and `X-Forwarded-For`,
  the customer's IP behind LiteSpeed, was sent. `production.py` restores those terms.
- `config.settings.base` keeps whatever environment a test reloaded it with. The
  settings tests that set a DSN reload it again with an empty DSN afterwards, or the
  next test to reload production would start a real Sentry client.
- An unhandled exception reaches Sentry twice, from Django's exception signal and
  from the `django.request` `ERROR` line; the SDK's de-duplication drops the second
  capture of the same exception object.
- Events carry no request id. Search the app's log for the event's time and route.
- An exception's message is sent as written. PostgreSQL's unique-violation detail
  names the duplicate value; no unique constraint on customer data reaches an
  unhandled error today, but a new one would.
- `pyproject.toml` requires `sentry-sdk>=2.74`, the version verified: an SDK without
  `data_collection` raises at `init`, and production would not boot.

---

## Data changes

None.

---

## Permissions

Sentry organisation membership controls who reads events. The DSN only allows
sending, and lives in each app's `.env`.

---

## Tests

- `apps/core/tests/test_logging.py` — the scrubber redacts the token from the URL and
  `Referer`, and leaves an event without a request unchanged.
- `tests/test_settings.py` — production starts no Sentry without a DSN, and starts it
  with exactly the collection settings above when one is set; `SENTRY_DSN` may be
  empty and `SENTRY_ENVIRONMENT` is required, like every other variable.

---

## Files

```text
config/settings/production.py
config/settings/base.py
config/settings/strict_env.py
config/settings/test.py
apps/core/logging.py
.env.example
render.yaml
pyproject.toml, uv.lock
apps/core/tests/test_logging.py
tests/test_settings.py
```
