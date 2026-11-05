# ADR 0023: Errors are reported to Sentry, without customer data

Status: Accepted

Date: 2026-11-05

Supersedes: None

---

## Context

Both cPanel environments are live (ADR 0022). An unhandled exception, or a failure the
code only logs (`email.send_failed`), was visible only to someone reading the app's
log on the host, so nobody learned of one until a customer complained. The host runs
no agents, so error tracking has to be a hosted service the app reports to.

Requests carry customer data that `convention.md` keeps off every log: checkout's
body and stack frames hold names, emails, phone numbers and addresses, the order
lookup posts an email, the admin's order search puts names, emails and phone numbers
in the query string, and the order page's URL carries the access_token, a bearer
credential under ADR 0003.

---

## Decision

- **Sentry** receives errors from `config.settings.production`, and only when
  `SENTRY_DSN` is set. Local, test and CI settings never initialise it.
- `SENTRY_DSN` may be empty (ADR 0008's `MAY_BE_EMPTY`), which turns reporting off.
  `SENTRY_ENVIRONMENT` is required and labels the deployment: `dev` or `production`.
- The SDK collects no user identity, cookies, request bodies, query parameters, SQL
  parameters or stack-frame variables, and filters client-IP headers such as
  `X-Forwarded-For` (`data_collection`).
- `scrub_sentry_event` (`apps/core/logging.py`) replaces UUIDs in the request URL and
  headers with `<redacted>` before an event leaves, as `RedactUUIDs` does for
  `django.request` log lines.
- Errors only: no performance tracing, profiling, session replay or Sentry Logs.

---

## Reason

Sentry's Django integration reports unhandled exceptions and every `ERROR` log line
with its traceback and an alert, without code at each call site. Its free plan covers
a shop this size. Collection is switched off per category rather than scrubbed per
field, so a new endpoint with new customer fields is safe without a change here.

---

## Alternatives considered

### Better Stack error tracking alongside its uptime and logs

Why it was not chosen: one vendor fewer, but Sentry's Django integration is the
established one, and its data-collection controls were verified against this code.

### `send_default_pii=False` with `max_request_body_size` and `include_local_variables`

Why it was not chosen: it sends the same data in sentry-sdk 2.74, but the SDK
deprecates `send_default_pii` in favour of `data_collection`.

---

## Consequences

### Positive

- An unhandled exception or an `ERROR` log line on either server raises a Sentry
  alert with its traceback, environment and route.
- No customer data, access_token or credential leaves the host with it.

### Negative

- Without frame variables, request bodies or query strings, an event shows where
  something failed but not with which input. The request id in the log line is the
  way back to the context.
- A third party holds stack traces and route names.

### Constraints introduced

- Never enable `send_default_pii`, frame variables, bodies or query parameters, and
  keep the client-IP header terms: an explicit `data_collection` does not add them.
- Re-check what an event carries after upgrading `sentry-sdk`; `data_collection` is
  new in 2.x and its defaults may change.

---

## Implementation

```text
config/settings/production.py
config/settings/base.py, strict_env.py, test.py
apps/core/logging.py (scrub_sentry_event)
.env.example, render.yaml
apps/core/tests/test_logging.py, tests/test_settings.py
docs/features/error-tracking.md
```

---

## Future reconsideration

If an error needs its input to be diagnosed often enough to matter, add an allowlist
of named, non-personal fields rather than reopening a whole category.
