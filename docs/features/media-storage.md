# Media storage

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Route uploaded images to Cloudinary, so that product photographs survive a deploy.

`architecture.md` requires this and treats it as settled. When this document was
written nothing implemented it — no `cloudinary` dependency, no `Pillow`, no
`STORAGES` setting, no `MEDIA_ROOT` — so an `ImageField` would have written to
the container's local disk, which Render replaces on every deploy. That is no
longer the case; see Implemented.

---

## Scope

What is included in this implementation?

- `cloudinary`, `cloudinary-storage`, and `Pillow` dependencies
- `STORAGES["default"]` pointing at Cloudinary, and the credential settings
- The ordering rule that uploads happen outside `transaction.atomic()`
- ~~A local development story that does not require Cloudinary credentials~~ —
  reversed by [ADR 0008](../decisions/0008-every-environment-variable-is-required.md); see Decisions
- `.env.example`, which `config/settings/base.py` already promises exists

What is explicitly outside the scope?

- The `ProductImage` model, which belongs to `product-catalog.md`
- Image transformation, resizing, or responsive variants
- Signed or expiring delivery URLs
- Any customer-facing upload endpoint. Only staff upload: product images and brand
  logos, through the admin API or the Django admin
- Cleaning up orphaned assets

---

## Context

`architecture.md` states three properties this feature must honour:

- **The filesystem is ephemeral.** Nothing written to local disk survives a deploy.
- **Uploads are synchronous**, inside the request, because there is no task queue.
- **Uploads must not happen inside `atomic()`.** An upload can take seconds, and
  holding a pooled Supabase connection open for that long exhausts the pool.

It also records the accepted consequence: if a transaction fails after a successful
upload, the asset is orphaned in Cloudinary. An orphaned asset is harmless; a
database row pointing at a missing image is not, and this ordering prevents that.

Most of this feature was built ahead of schedule by `staff-identity`, which needed
`Profile.avatar` and therefore needed somewhere for an upload to go. What remains
here is the catalogue-facing work, not the storage wiring.

---

## Planned

Delivered. Retained for the record of intent:

- Add `cloudinary`, `django-cloudinary-storage`, and `Pillow` to
  `pyproject.toml`
- Add `cloudinary` and `cloudinary_storage` to `INSTALLED_APPS`
- Read `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`
  in `config/settings/base.py` and nowhere else
- Set `STORAGES["default"]` to the Cloudinary backend, leaving `STORAGES["staticfiles"]`
  alone — static files are collected at build time and served from the container
- Override `STORAGES["default"]` to `FileSystemStorage` in
  `config/settings/test.py`, with a temporary `MEDIA_ROOT`, so the test suite never
  makes a network call
- Document the upload-before-transaction rule in `convention.md`'s Services section
  if it is not already unambiguous there

---

## Implemented

Delivered by `staff-identity` rather than by this feature, but complete and verified:

- `cloudinary`, `django-cloudinary-storage` and `Pillow` in `pyproject.toml`
- `cloudinary` and `cloudinary_storage` in `INSTALLED_APPS`
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET` read in
  `config/settings/base.py` and nowhere else
- `STORAGES["default"]` on the Cloudinary backend; `STORAGES["staticfiles"]` on
  WhiteNoise, collected at build time
- `MEDIA_URL` and `MEDIA_ROOT` in `base.py`
- `config/settings/test.py` overrides `STORAGES["default"]` to `FileSystemStorage`
  under a `tempfile.mkdtemp()` `MEDIA_ROOT`, so the suite makes no network call
- `config/settings/local.py` overrides it to `FileSystemStorage` too, so local
  development needs no Cloudinary credentials
- `.env.example` lists every variable `base.py` reads
- `DEFAULT_PARSER_CLASSES` remains JSON-only. Multipart parsing is enabled per view
  on the admin API's image and brand endpoints only (`admin-api.md`), which validate
  JPEG/PNG/WebP up to 5 MB. `add_product_image` uploads before it opens a
  transaction; admin logo uploads save inside the service's plain `save()`.
- `seed_demo` downloads its product photos and brand logos (falling back to a Pillow
  placeholder when a download fails) and saves them through the default storage.

Completed by this feature's own closing pass:

- `tests/test_storage.py`, which this document had promised and which did not
  exist: `test_default_storage_is_filesystem_under_test_settings` and
  `test_media_root_is_temporary_in_tests`
- `apps/core/checks.py`, a Django system check (`core.E001`) that fails startup
  when `STORAGES["default"]` is the Cloudinary backend and any of
  `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` or `CLOUDINARY_API_SECRET` is
  blank. Registered from `CoreConfig.ready()`. Local and test settings use
  `FileSystemStorage`, so the check stays silent there and needs no credentials
- `config/urls.py` appends `static(settings.MEDIA_URL, ...)`, which returns an
  empty list unless `DEBUG`, so a locally uploaded avatar finally has a working
  URL
- `apps/catalog/tests/test_models.py::test_product_image_persists_a_storage_reference`,
  the `ImageField` coverage this document deferred to a model whose image is the
  point

There are now two `ImageField`s: `Profile.avatar` (`apps/users/models.py`),
editable through the admin's `ProfileInline`, and `ProductImage.image`
(`apps/catalog/models.py`), which landed with `product-catalog.md`. Every rule in
this document — public permanent URLs, deletion orphaning the asset, upload
outside `atomic()` — applies to both.

---

## Remaining

Nothing. All three gaps recorded here are closed, and so is the missing test file
this document had promised.

One thing is deliberately **not** covered and never will be under the decision
below: no test exercises the real Cloudinary backend. A misconfiguration of
production storage is caught by `core.E001` at startup if a credential is blank,
but a credential that is present and *wrong* is still only discovered by deploying
and uploading an image.

---

## Decisions

### Decision: multipart parsing only where staff upload

**Decision**

`DEFAULT_PARSER_CLASSES` stays `JSONParser` only. `MultiPartParser` is set on
`ProductImageCreateView` and the brand list/detail views of the admin API.

**Reason**

Those are the only upload surfaces, and they are staff-only; every other route
stays JSON.

### Decision: tests use local filesystem storage, not Cloudinary

**Decision**

`config/settings/test.py` overrides `STORAGES["default"]` to `FileSystemStorage`
under a temporary directory.

**Reason**

A test suite that uploads to Cloudinary is slow, non-deterministic, requires
credentials in CI, and pollutes a real account with fixture images.

**Consequence**

Nothing in the test suite exercises the real Cloudinary path. A misconfiguration of
the production storage backend will not be caught by tests — only by the settings
refusing to import when a credential is blank, or by deploying and uploading an
image when one is merely wrong. [../handover.md](../handover.md#product-photos)
tells the merchant the part that affects them: removing a photo does not remove
the asset.

### Superseded: local development runs without Cloudinary credentials

> **Decision**
>
> `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET` default
> to empty strings, and `core.E001` reports blank credentials as a system-check
> error only when the Cloudinary backend is actually in use.
>
> **Reason**
>
> Local development and the test suite use `FileSystemStorage`, so requiring a
> Cloudinary account to run either would be a barrier for no benefit.
>
> **Consequence**
>
> A production misconfiguration surfaces at startup rather than at the first
> upload, without imposing credentials on anyone who is not uploading.

Superseded by [ADR 0008](../decisions/0008-every-environment-variable-is-required.md),
which makes every variable required in every environment. `core.E001` is removed:
settings that cannot import without the credentials make a check that verifies them
unreachable. The convenience this decision bought is gone — a developer now needs
Cloudinary values in `.env`, though any placeholder boots — and what replaces it is
that no deployment can start with a credential nobody noticed was missing.

This also bounds what `test_product_image_persists_a_storage_reference` can claim.
It asserts that an `ImageField` round-trips a stored reference and a retrievable
URL through *the configured default backend*, which under test settings is
`FileSystemStorage`. It is not evidence that Cloudinary works.

---

## Gotchas

- **Upload before opening the transaction, always.** This is the rule most likely
  to be violated, because the natural way to write a service is to open `atomic()`
  first. `architecture.md` and `convention.md` both state it; this is where it
  bites.
- Deleting a model row does **not** delete the Cloudinary asset. Storage grows
  monotonically with deletions and nothing reconciles the two stores.
- Cloudinary delivery URLs are **public and permanent**. Anyone with a URL can
  fetch the asset indefinitely. This is acceptable for product photography and
  would not be for anything private.
- A large upload occupies a gunicorn worker for its full duration, and there is no
  queue to move it to. On Render's smaller instances this measurably reduces
  concurrency.
- `STORAGES` is the Django 4.2+ setting. Do not use the removed
  `DEFAULT_FILE_STORAGE`, and do not set both.
- `Pillow` is required for `ImageField` validation even though Cloudinary does the
  storing. Without it, `ImageField` raises at model validation time.

---

## API

None. This feature adds no endpoints.

---

## Data changes

None. This feature configures storage; the models that use it are defined in
`product-catalog.md`.

---

## Permissions

None directly. The only write path is the Django admin, which requires `is_staff`.

Note the consequence of public delivery URLs: an image uploaded for an unpublished
product is reachable by anyone who has its URL, regardless of whether the product
is visible in the API. Do not treat unpublished as private.

---

## Tests

- `tests/test_storage.py::test_default_storage_is_filesystem_under_test_settings`
- `tests/test_storage.py::test_media_root_is_temporary_in_tests`
- `apps/core/tests/test_checks.py::test_filesystem_storage_does_not_require_cloudinary_credentials`
- `apps/core/tests/test_checks.py::test_complete_cloudinary_credentials_pass`
- `apps/core/tests/test_checks.py::test_blank_cloudinary_credential_is_an_error`
  — parametrised over all three credentials
- `apps/catalog/tests/test_models.py::test_product_image_persists_a_storage_reference`
- Coverage of the actual Cloudinary backend is deliberately absent — see the
  decision above

---

## Files

```text
config/settings/base.py
config/settings/test.py
config/urls.py
apps/core/checks.py
apps/core/apps.py
pyproject.toml
.env.example
tests/test_storage.py
apps/core/tests/test_checks.py
```

---

## Future context

This document exists separately from `product-catalog.md` because its three rules —
upload is synchronous, upload happens outside `atomic()`, deletion orphans the
asset — apply to **any** image anywhere in the system, not just product photos. A
later feature that adds a category banner or a lookbook inherits all three.

The known mitigation, if upload latency becomes a problem, is recorded in
`architecture.md`: upload directly from the browser to Cloudinary with a signed
upload preset, and have the API accept only the resulting reference. That moves the
upload off the worker entirely and is the natural next step.
