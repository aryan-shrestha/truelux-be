# ADR 0014: The database cache replaces Redis

Status: Accepted

Date: 2026-09-25

Supersedes: The Redis cache in `docs/architecture.md`

---

## Context

Redis was used for throttling and caching only. For a demo-scale shop it is one
more service to provision and pay for, and one more thing that can go down.

---

## Decision

`CACHES["default"]` uses `django.core.cache.backends.db.DatabaseCache` in a
`django_cache` table, created by `createcachetable` in the build command. `REDIS_URL`
is removed. The per-process throttle fallback, which existed only for Redis
outages, is removed.

---

## Reason

At this traffic level, Postgres absorbs throttle counters easily, and deployment
is Supabase + Render + Vercel + Cloudinary with nothing else.

---

## Alternatives considered

### Local-memory cache

Why it was not chosen: throttle counts would be per-process, so two workers would
double every limit.

---

## Consequences

### Positive

- One fewer service and one fewer environment variable.

### Negative

- Throttle checks add a small database write per request.

### Constraints introduced

- The build must run `createcachetable` before the service starts.

---

## Implementation

```text
config/settings/base.py
render.yaml
```
