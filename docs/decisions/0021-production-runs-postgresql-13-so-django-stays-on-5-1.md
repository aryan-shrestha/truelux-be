# ADR 0021: Production runs PostgreSQL 13, so Django stays on 5.1

Status: Accepted

Date: 2026-11-02

Supersedes: The `NULLS NOT DISTINCT` constraint of [ADR 0010](0010-shade-replaces-colour-and-is-optional.md)

---

## Context

The client is moving the API from Render to their cPanel shared host and its
database from Supabase to the host's PostgreSQL, which is 13.23. Django 5.2 requires
PostgreSQL 14 and refuses to connect to 13. Django 5.1 supports 13, but on anything
older than 15 it silently skips a `UniqueConstraint(nulls_distinct=False)`: the
migration succeeds and the variant uniqueness guarantee of ADR 0010 is gone.

---

## Decision

- `pyproject.toml` pins `django>=5.1,<5.2`. The lock resolves Django 5.1.15, and
  with it djangorestframework 3.17.2 and django-filter 25.1, whose newer releases
  require Django 5.2.
- `product_variant` replaces the `NULLS NOT DISTINCT` constraint with two partial
  unique constraints: `product_variant_unique_product_size_shade` on
  `(product, size, shade)` where `shade` is not null, and
  `product_variant_unique_product_size_shadeless` on `(product, size)` where `shade`
  is null. Migration `catalog/0004_variant_unique_without_nulls_not_distinct`.
- `docker-compose.yml` and CI run PostgreSQL 13, so the suite runs on production's
  major version.

---

## Reason

The client chose the host's database. Django 5.1 is the newest release that connects
to PostgreSQL 13, and the two partial constraints enforce on 13 exactly what
`NULLS NOT DISTINCT` enforced on 15: one variant per product, size and shade, and one
shadeless variant per product and size.

---

## Alternatives considered

### Keep the database on Supabase and move only the app

Why it was not chosen: the client wants the database on their host. It needs no
code change and keeps Django 5.2, so it remains the way back.

### Ask the host for PostgreSQL 15 or later

Why it was not chosen: not offered on the client's plan at the time of the move.

### Django 4.2

Why it was not chosen: it predates `nulls_distinct` and several APIs the code uses,
so it is a larger change for no gain. Its security support ended in April 2026 too.

---

## Consequences

### Positive

- The API runs on the client's host and database.
- The partial constraints work on every PostgreSQL version, so they need no change
  when the database is upgraded.

### Negative

- **Neither Django 5.1 nor PostgreSQL 13 receives security fixes.** Django 5.1's
  support ended in December 2025 and PostgreSQL 13 reached end of life in November
  2025. A vulnerability found in either from now on stays unpatched here.
- djangorestframework and django-filter are held below the releases that need
  Django 5.2.

### Constraints introduced

- Do not raise the Django pin while production runs PostgreSQL 13. Every supported
  Django release requires PostgreSQL 14 or later.
- Do not use `nulls_distinct`, or any other feature Django gates on PostgreSQL 14+,
  without checking that it fails loudly on 13 instead of being skipped.

---

## Implementation

```text
pyproject.toml, uv.lock
apps/catalog/models.py
apps/catalog/migrations/0004_variant_unique_without_nulls_not_distinct.py
apps/catalog/tests/test_shades_and_sizes.py
docker-compose.yml
.github/workflows/ci.yml
docs/features/shades-and-sizes.md
```

---

## Future reconsideration

As soon as the host offers PostgreSQL 14 or later, upgrade the database and move to
Django 5.2 LTS (supported until April 2028).
