# Demo seed

Status: Implemented

Last updated: 2026-09-29

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

- `apps/catalog/management/commands/_seed_catalogue.py` — the data: 24 real Korean
  brands (Round Lab, COSRX, Anua, Banila Co, Isntree, Beauty of Joseon, SKIN1004,
  Laneige, Sulwhasoo, Some By Mi, Illiyoon, Torriden, Etude, TIRTIR, Missha, rom&nd,
  Peripera, Mise en Scène, Lador, Aromatica, Nonfiction, Kundal, Kahi, Nature
  Republic); the category tree of the storefront design's mega-menu, 22 categories:
  - **Skincare** › Cleanse, Exfoliate, Treat & Masque, Tone, Hydrate, Eyes & Lips,
    Sun Care
  - **Makeup** › Face, Eyes, Lips
  - **Body** › Creams, Oils & Scrubs; Shower & Bath; Balms; Hands & Feet; Sun
    Protection
  - **Fragrance** › Perfume, Essential Oils
  - **Haircare** (no children)

  26 sizes; 38 of the brands' own shades (TIRTIR "21N Ivory", rom&nd "#06 Fig Fig",
  with approximate hex codes and brand-prefixed slugs); 6 skin types (Normal, Dry,
  Oily, Combination, Sensitive, Mature); 52 real products (COSRX Snail 96 Mucin
  Essence, Anua Heartleaf 77% Toner, Laneige Lip Sleeping Mask, Nonfiction eaux de
  parfum, Aromatica essential oils, …) at approximate Nepal retail prices in NPR, at
  least two published in every child category. Names, sizes and shades follow the
  brands' and retailers' listings. The cushion and lip tints have 4–6 shades;
  perfumes 50 and 100 ml; skincare is shadeless and sold by size. Every skincare and
  body product has 1–4 skin types, a `skin_feel` and its main INCI ingredients;
  makeup, fragrance and haircare have none. Each brand has `logo_urls` and each
  product `image_urls` (one tuple of candidate URLs per image, tried in order; 87
  photos in all). Six variants are on sale through `compare_at_price` (the `on_sale()`
  helper): three at base price (Anua cleansing oil, COSRX snail essence, SKIN1004
  ampoule 55 ml) and three at an override (Clean It Zero 180 ml, Beauty of Joseon
  Glow Serum 60 ml, Anua toner 500 ml); `seed_demo` writes the field.
  `RETIRED_BRAND_SLUGS` and `RETIRED_PRODUCT_SLUGS` list the invented
  catalogue an earlier version seeded.
- `apps/catalog/management/commands/seed_demo.py` — creates brands, sizes, shades
  and skin types with `get_or_create`; upserts every seeded category (`parent`,
  `name`, `sort_order`) and every seeded product (scalar fields, `category`, skin
  types) with `update_or_create`, so a row that already existed is brought back to
  the seed tree. Variants and images are only created with a new product.
  `fetch_image` downloads each product photo and brand logo (stdlib `urllib`, a
  browser `User-Agent`, 15 s timeout) and keeps it only if Pillow reads it as JPEG,
  PNG or WebP; the file extension comes from that format. When every candidate URL
  for an image fails, the command writes a warning and saves a generated PNG instead
  (800×1000 for a product, 400×400 for a logo: a gradient in the brand's palette with
  the initials and an ASCII-folded caption), so one dead URL cannot fail a build. No
  image files in the repository. `--flush` deletes the seeded and retired products,
  then every seeded category (current or retired: `RETIRED_CATEGORY_SLUGS` lists the
  earlier Cleansers, Serums and Moisturisers) that no longer holds a product, so the
  tree is recreated exactly, then every retired brand no product refers to. Current
  brands, sizes, shades and skin types are never flushed.
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
sizes, several variants at or below the low-stock threshold (5), and six variants on
sale, priced by override and by base price (`sale-prices.md`).

**Reason**

The storefront and the admin app must render those states; a tidy fixture hides them.

### Decision: real products and photos, downloaded at seed time

**Decision**

The catalogue is real Korean cosmetics. `seed_demo` downloads the photos and logos
from the brands' stores and K-beauty retailers (Shopify CDNs, thekshop.ca,
sokoglam.com, stylejolly.com) when it creates a product or brand. This replaces the
earlier invented brands and generated placeholder images.

**Reason**

A client demo reads as a real shop only with real products. Downloading instead of
committing keeps about 13 MB of images the project does not own out of git, and
matches how the build already uploads images to Cloudinary.

**Trade-off**

The seed needs outbound network access, and a store can move or delete a photo. Each
image lists fallback URLs, and a placeholder takes over when all of them fail.

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
- Reseeding locally leaves the previous image files in `media/` (the storage
  appends a suffix); delete the folder if it matters.
- The photos and logos belong to the brands. They are fine for a demo, but the
  merchant's real catalogue and photographs come in through `import_catalogue`
  (ADR 0016), never through this seed.
- A "No image downloaded for …; saved a placeholder." warning means every URL for
  that image failed; replace the URL in `_seed_catalogue.py`. A download failure is
  never an error.
- Downloads run inside the seed's transaction, so a slow CDN keeps it open longer;
  a full seed downloads about 110 files.
- A demo database seeded with the invented catalogue is not updated by `--deploy`,
  which only seeds an empty catalogue: it needs an empty database. Locally,
  `make reseed` removes the invented products and brands.
- Shades and sizes of the invented catalogue stay in an existing database, since
  shades and sizes are never flushed; nothing refers to them.
- `make seed`/`make reseed` use `config.settings.dev`, whose database and media come
  from `.env`. Point them at a local database first, or they write to whatever `.env`
  names (Supabase and Cloudinary on the owner's machine).
- Seeded emails use `seed.invalid`, which can never resolve.
- `conftest.py` replaces `seed_demo.fetch_image` for every test with a stub that
  returns a 10×10 PNG, so the suite never touches the network. A test of
  `fetch_image` itself must bind the real function at import.
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
  shadeless skincare, the awkward cases, the six sale variants (in the data and once
  seeded), idempotence, flush (including a retired
  category and a re-parented one, keeping a category a merchant product uses, and
  re-parenting that surviving category), restoring an edited seeded category and
  product without `--flush`,
  one primary per product, stored images and logos are the downloaded bytes, a
  placeholder when every download fails, `fetch_image` returning a PNG's bytes and
  extension and `None` for an HTML page or a network error, `--flush` removing the
  retired invented products and brands; `--deploy` seeds an empty catalogue
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
conftest.py                              offline stub for fetch_image
apps/users/management/commands/seed_staff.py
Makefile
render.yaml
```
