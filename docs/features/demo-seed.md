# Demo seed

Status: Implemented

Last updated: 2026-09-26

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
- `--deploy` on all three commands, which the Render build runs so a fresh demo
  deploy gets the same data (ADR 0015)

What is explicitly outside the scope?

- Production data. Every command refuses to run outside `DEBUG`, except with
  `--deploy` while `SEED_DEMO_DATA` is true.

---

## Implemented

- `apps/catalog/management/commands/_seed_catalogue.py` — the data: 8 invented
  brands (Lumière, Verde Botanics, Kaya Rose, Nordic Dew, Saffron & Co., Aurum,
  Mistral, Bloom Theory); the category tree of the storefront design's mega-menu,
  22 categories:
  - **Skincare** › Cleanse, Exfoliate, Treat & Masque, Tone, Hydrate, Eyes & Lips,
    Sun Care
  - **Makeup** › Face, Eyes, Lips
  - **Body** › Creams, Oils & Scrubs; Shower & Bath; Balms; Hands & Feet; Sun
    Protection
  - **Fragrance** › Perfume, Essential Oils
  - **Haircare** (no children)

  15 sizes; 23 shades with hex codes; 6 skin types (Normal, Dry, Oily, Combination,
  Sensitive, Mature); 48 products priced in NPR, at least two published in every child
  category. Foundations and lipsticks have 4–6 shades; perfumes 50 and 100 ml;
  skincare is shadeless and sold by size. Every skincare and body product has 1–4
  skin types, a `skin_feel` and an INCI-style `key_ingredients` line; makeup,
  fragrance and haircare have none.
- `apps/catalog/management/commands/seed_demo.py` — creates brands, sizes, shades
  and skin types with `get_or_create`; upserts every seeded category (`parent`,
  `name`, `sort_order`) and every seeded product (scalar fields, `category`, skin
  types) with `update_or_create`, so a row that already existed is brought back to
  the seed tree. Variants and images are only created with a new product. Generates
  each product image (800×1000) and brand logo (400×400) as a PNG with Pillow: a gradient in the brand's palette with the
  initials and an ASCII-folded brand caption. No network access, no image files in
  the repository. `--flush` deletes the seeded products, then every seeded category
  (current or retired: `RETIRED_CATEGORY_SLUGS` lists the earlier Cleansers, Serums
  and Moisturisers) that no longer holds a product, so the tree is recreated exactly.
  Brands, sizes, shades and skin types are never flushed.
- `apps/orders/management/commands/seed_orders.py` — 17 orders placed through
  `place_order`, moved through `transition_order`, COD payments recorded (completed
  for delivered orders), then back-dated across the last 29 days so the dashboard has
  a history. `--flush` and `--flush-only` delete orders at `@seed.invalid`.
- `Makefile` — `seed`, `reseed`, `seed-staff`.
- `--deploy` (ADR 0015) on `seed_demo`, `seed_orders` and `seed_staff`: bypasses the
  `DEBUG` guard only when `SEED_DEMO_DATA` is true, and is otherwise a no-op that
  exits 0. It never flushes (argparse rejects it with `--flush`/`--flush-only`).
  `seed_demo --deploy` seeds only when there are no brands, categories or products;
  `seed_orders --deploy` only when there are no orders and every product is a
  seeded one, and sends its email to the dummy backend. Images go through the
  default storage, so on Render they land in Cloudinary. `render.yaml` runs all
  three after `createcachetable`.

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
- `--deploy` treats any brand, category or product as a merchant's catalogue and
  seeds nothing, because seeding upserts by slug. A demo that should be reseeded
  needs an empty catalogue.
- Deleting every order in a demo whose products are all seeded makes the next
  build seed orders again.
- A seeded category that still holds a product the merchant (or an e2e run) added
  survives `--flush`, and when its parent is flushed `SET_NULL` turns it into a
  root. Seeding re-parents it, which is why categories are upserted rather than
  `get_or_create`d.
- Seeding overwrites staff edits to a seeded category's or seeded product's name,
  parent, category, price, published flag or sort order. The seed owns those rows.

---

## Permissions

DEBUG only, or `--deploy` with `SEED_DEMO_DATA` true.

---

## Tests

- `apps/catalog/tests/test_seed_demo.py` — DEBUG guard, brands with logos, the
  category tree in menu order, two published products per child category, skin types
  and care details on skincare and body products, shade counts, perfume sizes,
  shadeless skincare, the awkward cases, idempotence, flush (including a retired
  category and a re-parented one, keeping a category a merchant product uses, and
  re-parenting that surviving category), restoring an edited seeded category and
  product without `--flush`,
  one primary per product, generated PNGs; `--deploy` seeds an empty catalogue
  outside DEBUG through the default storage, is a no-op while `SEED_DEMO_DATA` is
  false, leaves an existing catalogue alone, and refuses `--flush`.
- `apps/orders/tests/test_seed_orders.py` — every status present, a payment per
  order, cash collected only for delivered orders, stock arithmetic, flush
  behaviour, the reseed sequence, dates spanning the dashboard window; `--deploy`
  seeds without sending mail, is a no-op while `SEED_DEMO_DATA` is false, once
  orders exist, beside a merchant product (whose stock is untouched), and on an
  empty catalogue.

---

## Files

```text
apps/catalog/management/commands/{seed_demo,_seed_catalogue}.py
apps/orders/management/commands/seed_orders.py
apps/users/management/commands/seed_staff.py
Makefile
render.yaml
```
