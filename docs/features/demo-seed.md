# Demo seed

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Give a developer and both front-end apps a realistic cosmetics catalogue, a month
of orders and a staff login on a fresh database, with one command each.

---

## Scope

What is included in this implementation?

- `make seed`: `seed_demo` (catalogue) then `seed_orders` (orders)
- `make reseed`: flush orders, flush and reseed the catalogue, reseed orders
- `make seed-staff`: the demo staff user (see `staff-auth.md`)

What is explicitly outside the scope?

- Production data. Every command refuses to run outside `DEBUG`.

---

## Implemented

- `apps/catalog/management/commands/_seed_catalogue.py` — the data: 8 invented
  brands (Lumière, Verde Botanics, Kaya Rose, Nordic Dew, Saffron & Co., Aurum,
  Mistral, Bloom Theory), the category tree Skincare (Cleansers, Serums,
  Moisturisers), Makeup (Face, Eyes, Lips), Haircare, Fragrance, Body; 14 sizes;
  23 shades with hex codes; 33 products priced in NPR. Foundations and lipsticks have
  4–6 shades; perfumes 50 and 100 ml; skincare is shadeless and sold by size.
- `apps/catalog/management/commands/seed_demo.py` — creates the rows with
  `get_or_create`, generates each product image (800×1000) and brand logo
  (400×400) as a PNG with Pillow: a gradient in the brand's palette with the
  initials and an ASCII-folded brand caption. No network access, no image files in
  the repository. `--flush` deletes the seeded products.
- `apps/orders/management/commands/seed_orders.py` — 17 orders placed through
  `place_order`, moved through `transition_order`, COD payments recorded (completed
  for delivered orders), then back-dated across the last 29 days so the dashboard has
  a history. `--flush` and `--flush-only` delete orders at `@seed.invalid`.
- `Makefile` — `seed`, `reseed`, `seed-staff`.

---

## Remaining

None.

---

## Decisions

### Decision: the awkward cases are seeded on purpose

**Decision**

One unpublished product, one sold out, one without images, several `price_override`
sizes, and several variants at or below the low-stock threshold (5).

**Reason**

The storefront and the admin app must render those states; a tidy fixture hides them.

### Decision: orders go through the services, the catalogue through the models

**Decision**

`seed_orders` uses the real placement and transition services and only rewrites
`created_at`; `seed_demo` writes models directly.

**Reason**

Order history is only realistic if stock, numbers and payments come from the code
that produces them; catalogue rows have no business rule beyond constraints.

---

## Gotchas

- `seed_demo --flush` fails while seeded orders reference its variants; `make reseed`
  runs `seed_orders --flush-only` first.
- Reseeding locally leaves the previous generated files in `media/` (the storage
  appends a suffix); delete the folder if it matters.
- Seeded emails use `seed.invalid`, which can never resolve.

---

## Permissions

DEBUG only.

---

## Tests

- `apps/catalog/tests/test_seed_demo.py` — DEBUG guard, brands with logos, the
  category tree, shade counts, perfume sizes, shadeless skincare, the awkward cases,
  idempotence, flush, one primary per product, generated PNGs.
- `apps/orders/tests/test_seed_orders.py` — every status present, a payment per
  order, cash collected only for delivered orders, stock arithmetic, flush
  behaviour, the reseed sequence, dates spanning the dashboard window.

---

## Files

```text
apps/catalog/management/commands/{seed_demo,_seed_catalogue}.py
apps/orders/management/commands/seed_orders.py
apps/users/management/commands/seed_staff.py
Makefile
```
