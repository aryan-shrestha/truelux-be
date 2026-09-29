# ADR 0015: The build seeds demo data when `SEED_DEMO_DATA` is true

Status: Accepted

Date: 2026-09-26

Supersedes: The "demo staff variables are required in production too" decision in
`docs/features/deployment.md`, and the DEBUG-only rule for the seed commands in
`docs/features/demo-seed.md` and `docs/features/staff-auth.md`

---

## Context

`seed_demo`, `seed_orders` and `seed_staff` refuse to run outside `DEBUG`, so that a
mistyped `DJANGO_SETTINGS_MODULE` cannot put invented products, orders or a known
staff password into a real shop. Render's free tier has no shell and no one-off
jobs, so a fresh deploy for a client demo had an empty catalogue and no way to sign
in to the admin app.

---

## Decision

Each seed command takes a `--deploy` flag, and the `render.yaml` build runs
`seed_staff --deploy`, `seed_demo --deploy` and `seed_orders --deploy` after
`migrate` and `createcachetable`.

`--deploy` bypasses the `DEBUG` guard only when the new required variable
`SEED_DEMO_DATA` is true; when it is false the command prints a line and exits 0, so
the build carries on. It is idempotent and conservative:

- `seed_staff --deploy` creates `DEMO_STAFF_EMAIL` only if no user has that email,
  never resets a password, and rejects a `DEMO_STAFF_PASSWORD` under 12 characters.
- `seed_demo --deploy` seeds only when there are no brands, categories or products.
  It cannot be combined with `--flush`.
- `seed_orders --deploy` seeds only when there are no orders and every product is a
  seeded one, with email sent to the dummy backend. It cannot be combined with
  `--flush` or `--flush-only`.

Images are saved through the default storage, which is Cloudinary in production.

---

## Reason

The build is the only process on the free tier that runs with the production
environment and a database connection. Running it on every deploy is only safe if
every run after the first does nothing, and if nothing it does can reach a row the
merchant created: `seed_demo` upserts by slug and `seed_orders` takes stock, so both
refuse unless the data they would touch is absent or their own.

The explicit variable keeps the `DEBUG` guard's purpose. Seeding a production
database now needs a deliberate `SEED_DEMO_DATA=true`, not an accident.

---

## Alternatives considered

### Seed from a data migration

Why it was not chosen: migrations run in every environment including the test
database, cannot be switched off per deployment, and would put generated images
and a staff password into migration history.

### Allow the plain commands whenever `SEED_DEMO_DATA` is true

Why it was not chosen: the plain commands flush and reset. `seed_staff` would reset
the staff password on every deploy, undoing any change staff made.

---

## Consequences

### Positive

- A new demo deploy comes up with the catalogue, a month of orders and a staff
  login, with no manual step.

### Negative

- The first build with `SEED_DEMO_DATA=true` downloads about 110 product photos and
  brand logos and uploads them to Cloudinary, which makes that build slower. (Before
  2026-09-29 the images were generated placeholders; see `features/demo-seed.md`.)
- A demo shop runs with a known staff email; the password is whatever the operator
  put in `DEMO_STAFF_PASSWORD`.

### Constraints introduced

- `SEED_DEMO_DATA` is required everywhere (ADR 0008); `render.yaml` sets it to
  `"true"`. A real shop sets it to `"false"`.
- `DEMO_STAFF_PASSWORD` must be at least 12 characters whenever the build seeds.
- Deleting every order in a demo whose catalogue is still all seeded makes the next
  build seed orders again.

---

## Implementation

```text
config/settings/base.py
.env.example
render.yaml
apps/users/management/commands/seed_staff.py
apps/catalog/management/commands/seed_demo.py
apps/orders/management/commands/seed_orders.py
tests/test_settings.py
```

---

## Future reconsideration

When the service moves off the free tier: a one-off job or `preDeployCommand` could
run the seed instead of the build.
