# ADR 0016: The real catalogue is imported from a workbook, from the owner's machine

Status: Accepted

Date: 2026-09-26

Supersedes: None

---

## Context

The client's real catalogue (brands, categories, products, variants, stock and
photographs) has to reach production before the demo. The client works in Excel,
and there is no bulk upload in the admin app. Render's free tier has no shell and no
jobs, so nothing can run a one-off command on the server. The seed commands refuse to
run outside `DEBUG` and write models directly.

## Decision

**The catalogue arrives as one `.xlsx` workbook, loaded by `manage.py
import_catalogue`, run from the owner's machine against the production database and
Cloudinary.**

- The workbook layout is defined once, in `apps/catalog/workbook/layout.py`, and both
  `export_catalogue` and `import_catalogue` use it.
- The import validates the whole workbook before it writes anything, and writes
  nothing if any row is wrong.
- It **upserts** and **never deletes**, so it can be run again after a correction.
- Every write goes through `apps.catalog.services` (ADR 0002), in one
  `transaction.atomic()`. Images upload **after** the commit (`media-storage.md`).
- It has **no `DEBUG` guard**: writing the merchant's catalogue into production is
  its purpose.
- `ENV_FILE` points the settings at `.env.production` (gitignored) instead of
  `.env`, so the command runs with production's variables and
  `config.settings.production`.

## Reason

A workbook is the one format the client already uses, and exporting the demo
catalogue into the same layout gives them a filled example. Running from the owner's
machine needs no new infrastructure: the database and Cloudinary are both reachable
from anywhere with the credentials. Validate-then-write keeps a half-loaded
catalogue out of production, and upserts make the obvious recovery ("fix the cell,
run it again") safe.

## Alternatives considered

### An upload endpoint in the admin app

Why it was not chosen: it needs UI, multipart handling of a workbook plus a folder of
images, and a request long enough to upload every photograph. There is no task queue
to move that off the request. A command does the same job for a one-time load.

### CSV files

Why it was not chosen: one file per sheet, no dropdowns, no header comments, and
Excel mangles encodings and leading zeros. A single workbook is easier for the client.

### Extending `seed_demo`

Why it was not chosen: the seed commands exist to write demo rows and refuse to run
outside `DEBUG` precisely so they cannot touch a real shop.

## Consequences

### Positive

- Loading, correcting and reloading the catalogue is one command, and a dry run
  shows the counts first.
- The import exercises the same service rules as the admin API, including the
  refusal to publish a product without variants.

### Negative

- Anyone holding `.env.production` holds every production secret. It must never be
  committed, and it lives only on the owner's machine.
- Removing a product still happens in the admin app: the import only reports what the
  workbook no longer lists.
- Images upload one at a time from a laptop connection; a large catalogue takes a
  while, and a failed upload has to be retried by running the import again.

### Constraints introduced

- The workbook columns are defined only in `layout.py`.
- The importer must not write models directly; a missing write belongs in
  `apps.catalog.services`.
- `ENV_FILE` is the third exception in `convention.md`'s settings rules.

## Implementation

```text
apps/catalog/workbook/{layout,export,reader,validation,importer}.py
apps/catalog/management/commands/{export_catalogue,import_catalogue}.py
config/settings/base.py                 ENV_FILE
Makefile                                catalogue-template, catalogue-export, catalogue-import
docs/features/catalogue-import.md
```

## Future reconsideration

Revisit when the merchant needs to load catalogues regularly rather than once: that
is the point at which an upload screen in the admin app earns its cost.
