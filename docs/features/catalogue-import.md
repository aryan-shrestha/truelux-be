# Catalogue import and export

Status: Implemented

Last updated: 2026-09-26

---

## Goal

The client fills an Excel workbook with the real catalogue, and the owner seeds the
database from it: locally, and against production (Supabase and Cloudinary) from the
owner's machine. The same workbook, exported from a database, shows the client a fully
filled example and lets a catalogue make the round trip.

---

## Scope

What is included in this implementation?

- One `.xlsx` layout, defined once in code and shared by export and import
- `manage.py export_catalogue <out.xlsx> [--template]`
- `manage.py import_catalogue <file.xlsx> [--images <dir>] [--dry-run] [--replace-images]`
- `make catalogue-template`, `make catalogue-export`, `make catalogue-import`
- `ENV_FILE`, so a command can read `.env.production` instead of `.env`

What is explicitly outside the scope?

- Deleting rows that are not in the workbook: they are reported and left alone
- Moving a variant to another product, or a category to another parent
- An upload screen in the admin app; this is an owner's command-line tool
  ([ADR 0016](../decisions/0016-the-real-catalogue-is-imported-from-a-workbook.md))
- Orders, payments, staff

---

## Context

Writes go through `apps.catalog.services` (ADR 0002); images upload outside any
transaction (`media-storage.md`); the image limits are the admin API's (JPEG, PNG or
WebP, 5 MB), now in `apps/catalog/constants.py` and shared by both.

---

## Implemented

- `apps/catalog/workbook/layout.py` — the single definition: sheet order, each
  column's header, required flag, kind (text, whole number, price, Yes/No, hex),
  width, header comment, max length and dropdown source; the example row of each
  sheet; the six prefilled skin types; the read-me text.
- `apps/catalog/workbook/export.py` — `build_workbook(rows)` writes the layout with
  openpyxl: Arial as the workbook's Normal font, bold header row (charcoal and white
  when required, light grey when optional) with a comment per header, row 1 frozen,
  column widths, a grey italic example row 2 with an "ignored" note, and data
  validation on rows 3–1000: dropdowns referencing the other sheets' Name columns
  (`'Brands'!$A$3:$A$1000`; Categories' Parent references its own Name column),
  Yes/No lists, whole numbers ≥ 0 for Stock and Sort order, decimals ≥ 0 for prices,
  each with a friendly error. No cell formulas. `template_rows()` fills only the skin
  types; `catalogue_rows()` exports every brand, category (parents first), shade,
  size, skin type, product and variant. Image and logo cells hold the stored names'
  basenames, the primary image first; alt text is the first image's.
- `apps/catalog/workbook/reader.py` — reads each sheet by header name, skips row 2
  and blank rows, trims text, and parses each cell by kind, accepting numbers typed as
  text and `yes`/`YES`/`Y`/`no`/`N`. Each problem is a `Problem` that prints as
  `Sheet "Products", row 7, column "Brand": "Lumiere" is not on the Brands sheet`.
- `apps/catalog/workbook/validation.py` — `Catalogue` reads the database once;
  `Validator` checks required cells, duplicates (brand, shade, size and skin-type
  names; product names by slug; SKUs; category name + parent), references to other
  sheets or to rows already in the database, one-level category depth, ambiguous
  category names, a variant naming an unknown product, an SKU that already belongs to
  another product, the (product, size, shade) uniqueness against the sheet and the
  database, a price override of 0, a published product with no variants
  (`ProductHasNoVariants.message`), and every image that will be uploaded: a plain
  file name, present in `--images` under exactly that name, ≤ 5 MB, JPEG/PNG/WebP by
  its content.
- `apps/catalog/workbook/importer.py` — `import_catalogue` reads, validates, and
  returns the problems without writing if there are any. Otherwise it upserts in one
  `transaction.atomic()` through `create_taxonomy_entry`/`update_taxonomy_entry`,
  `create_product`/`update_product`, `create_variant`/`update_variant` and
  `set_variant_stock`, calling an update service only with the fields that changed.
  Products are created unpublished and published after their variants exist, so the
  service's own rule holds. `--dry-run` runs the same writes and rolls back, so its
  counts are real. After the commit, logos go through `update_taxonomy_entry` and
  product images through `add_product_image` (first successful upload primary);
  `--replace-images` then deletes the old images with `delete_product_image`, only if
  every new one arrived. An `OSError` or Cloudinary error is reported per file and the
  rest continue.
- `apps/catalog/management/commands/export_catalogue.py`, `import_catalogue.py` —
  the commands. Import prints every problem to stderr and exits non-zero; on success
  it prints created/updated/unchanged per sheet, the rows not in the workbook, and
  images uploaded (or, in a dry run, to be uploaded). A failed upload exits non-zero
  after the summary.
- `config/settings/base.py` — `ENV_FILE` chooses the env file; a named file that does
  not exist refuses to import.
- `Makefile` — `catalogue-template [OUT=…]`, `catalogue-export [OUT=…]`,
  `catalogue-import FILE=… [IMAGES=…] [ARGS="--dry-run --replace-images"]`.
- `.gitignore` — `.env.production` and `*.xlsx`.

---

## Remaining

None.

---

## Decisions

### Decision: matching keys

**Decision**

Brands, shades, sizes and skin types match by exact name; categories by name and
parent; products by the slug of their name, falling back to an exact, unique name
(a product created in the admin app may have its own slug); variants by SKU. A new
product's slug is exactly `slugify(name)`, so the next run finds it.

**Consequence**

Renaming a product in the workbook creates a new product and reports the old one as
not in the workbook. A category under a different parent is a different category.

### Decision: the workbook is authoritative for the columns it has

**Decision**

A blank optional cell means its default: empty text, sort order 0, brand active,
product unpublished, no price override. Blank image and logo cells leave the
existing files alone.

### Decision: images only where there are none

**Decision**

A product or brand gets the workbook's files only when it has none, unless
`--replace-images`. Files are only checked when they will be uploaded, so an
exported workbook imports cleanly without the images folder.

### Decision: stock always goes through `set_variant_stock`

**Decision**

A new variant is created with 0 and then set, so every imported stock figure has the
service's `catalog.stock_set` audit line.

---

## Gotchas

- The import runs under whatever `DJANGO_SETTINGS_MODULE` and env file it is given.
  **Check which database `.env` points at before running anything**: `.env` is not
  necessarily local.
- A dry run logs the services' `catalog.*` lines even though it rolls back.
- After a partly failed upload, a product that got some of its images is skipped
  on the next run; use `--replace-images` for it.
- Deleting or replacing an image leaves the Cloudinary asset (`media-storage.md`).
- The dropdowns cover rows 3–1000. The importer reads every row regardless.
- Excel may store a number typed into a text column (an SKU like `10023`) as a float;
  the reader turns `10023.0` back into `10023`.

---

## Importing into production

Run from the owner's machine. Nothing is committed.

1. Create `.env.production` in the repository root (gitignored). It holds every
   variable in `.env.example`, with production's values: `DATABASE_URL` and
   `DATABASE_DIRECT_URL` from Supabase, the Cloudinary keys, the production
   `DJANGO_SECRET_KEY`, and `SEED_DEMO_DATA=false`.
2. Set `SEED_DEMO_DATA` to `false` in the Render dashboard too, before the next
   deploy, so the build does not also seed demo products into the real shop
   (ADR 0015; it seeds only an empty catalogue, but import first and it is moot).
3. Dry run:

   ```bash
   ENV_FILE=.env.production DJANGO_SETTINGS_MODULE=config.settings.production \
     make catalogue-import FILE="TrueLux catalogue.xlsx" IMAGES=images/ ARGS=--dry-run
   ```

4. Fix every reported problem in the workbook and repeat until the dry run is clean.
5. Run the same command without `ARGS=--dry-run`. Images upload to Cloudinary after
   the database commit. Running it again is safe.

`ENV_FILE` replaces `.env` entirely; a variable missing from `.env.production` fails
at import rather than falling back to the local value.

---

## Permissions

Whoever holds the database and Cloudinary credentials. There is no API.

---

## Tests

- `apps/catalog/tests/test_catalogue_workbook.py`
  - the template: sheet order, headers, fills, fonts, comments, frozen row, the
    example row, prefilled skin types, dropdown, Yes/No, whole-number and decimal
    validations, no formulas;
  - import creates the catalogue; the example row is ignored; export → import →
    import changes nothing; changed fields are updated and the rest counted
    unchanged; stock on new and existing variants goes through `set_variant_stock`;
    rows missing from the workbook are reported and kept; `--dry-run` writes
    nothing; loose spellings and numbers as text; references to database rows;
  - 31 validation cases, each asserting its sheet/row/column message and that nothing
    was written; all problems reported at once; images without `--images`; an SKU of
    another product; a missing sheet or column; a file that is not a workbook;
  - images and logos uploaded, first primary; kept without `--replace-images`,
    replaced with it; uploads happen outside any transaction, after the rows exist;
    a failed upload is reported and the rest continue.
- `tests/test_settings.py` — `ENV_FILE` chooses the file read; a missing one fails.

---

## Files

```text
apps/catalog/constants.py
apps/catalog/workbook/{layout,export,reader,validation,importer}.py
apps/catalog/management/commands/{export_catalogue,import_catalogue}.py
apps/catalog/tests/test_catalogue_workbook.py
config/settings/base.py
Makefile
docs/decisions/0016-the-real-catalogue-is-imported-from-a-workbook.md
```
