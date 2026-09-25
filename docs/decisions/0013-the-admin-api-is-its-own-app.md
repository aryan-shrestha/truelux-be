# ADR 0013: The admin API is its own app

Status: Accepted

Date: 2026-09-25

Supersedes: None

---

## Context

`CLAUDE.md` fixes the app set and requires an ADR to add one. The admin API is an HTTP
surface over several domains: the catalogue, orders and the dashboard.

---

## Decision

Add `apps/backoffice`, with views, serializers, selectors and URLs only, and no
models. It reads through its own selectors and writes only through the services of
`catalog` and `orders`.

---

## Reason

Staff endpoints have different permissions, representations (stock counts, ids,
unpublished rows) and throttles from the public ones. Keeping them apart stops a
public serializer from ever gaining a staff-only field by accident.

---

## Alternatives considered

### Admin views inside each domain app

Why it was not chosen: public and staff serializers would sit side by side, and a
field leak becomes a one-line mistake.

---

## Consequences

### Positive

- Everything under `/api/v1/admin/` is in one place, with one permission policy.

### Negative

- One more app.

### Constraints introduced

- `backoffice` owns no models and never writes a model directly.

---

## Implementation

```text
apps/backoffice/
config/urls.py
```
