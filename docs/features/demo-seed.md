# Demo seed

Status: Implemented

Last updated: 2026-09-24

---

## Goal

Give a developer a working shop to develop against: a catalogue, because a fresh
database cannot hold a single sellable product, and an order history, because
without one `OrderAdmin` and `PaymentAdmin` are empty pages and none of the
merchant's daily duties can be practised.

---

## Scope

What is included in this implementation?

- `manage.py seed_demo`, refusing to run outside `DEBUG`
- Sizes, colours, a two-level category tree, nine products, their variants and
  their images
- The awkward catalogue shapes a storefront has to survive
- `manage.py seed_orders` — an order in every status, with its payment
- `--flush` on each, to delete what it created and seed again
- `make seed` and `make reseed`
- Placeholder photography, with its licensing recorded

What is explicitly outside the scope?

- **Users.** Nothing here creates one; `make superuser` does
- ~~Orders and payments.~~ Originally out of scope, on the grounds that the
  catalogue was the blocker. It was the blocker for the storefront, not for the
  admin: every merchant workflow in `../handover.md` needs an order to act on, and
  there was no way to get one without checking out by hand. `seed_orders` closes
  that
- Any production path. This is a development tool
- The merchant admin, which belongs to `merchant-admin.md` and is the real fix
- Fixtures for the test suite, which uses factories

---

## Context

[ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md) made `size`
and `color` lookup tables, and `product-catalog.md` records the consequence:
both ship empty, and **an empty `size` table means no `ProductVariant` can be
created at all**. Until `merchant-admin.md` (#10) lands, the Django shell is the
only way in.

That makes a fresh database useless to anyone building against the API. The
storefront repository hit exactly this: its catalogue endpoints work perfectly
and return nothing.

This command is the stopgap. It is not a substitute for the admin — a merchant
cannot use it, and it creates invented garments — but it removes the blocker for
development.

---

## Implemented

- `apps/catalog/management/commands/seed_demo.py` — the command, with `SIZES`,
  `COLORS`, `CATEGORIES` and a `PRODUCTS` tuple of frozen dataclasses
- `apps/catalog/management/commands/seed_assets/` — twelve 1200×1500 photographs
  and a `LICENSE.md` crediting each
- `apps/orders/management/commands/seed_orders.py` — the order history, as an
  `ORDERS` tuple of frozen dataclasses
- `Makefile` — `seed` runs both commands; `reseed` flushes and re-seeds in the
  order the foreign keys demand
- `apps/catalog/tests/test_seed_demo.py` — 10 tests
- `apps/orders/tests/test_seed_orders.py` — 13 tests

`seed_demo` creates 6 sizes, 5 colours, 2 root categories with 2 children each,
9 products, 37 variants and 13 images. `seed_orders` then places 7 orders — one
in each of the five statuses, across both payment methods — and their payments.

---

## Remaining

None.

The real answer to the empty-catalogue problem was `merchant-admin.md` (#10), and
it has landed. `SizeAdmin` and `ColorAdmin` exist, a merchant populates the lookup
tables themselves, and this command's reason for existing has narrowed exactly as
predicted: from "nothing can populate these" to "give a developer something to look
at". Still worth having, and a much smaller claim.

One consequence worth noting: the SKUs this command writes (`BLT-M-BLA`) are not
the ones #10's "Generate variants" action produces (`BOXY-LOGO-TEE-M-BLACK`). Demo
rows, so it does not matter, but do not read the difference as a bug.

---

## Decisions

### Decision: it refuses to run outside DEBUG

**Decision**

`handle()` raises `CommandError` when `settings.DEBUG` is false, before anything
is written.

**Reason**

The command writes rows. A mistyped `DJANGO_SETTINGS_MODULE` would otherwise put
invented garments into a real shop, and there is no undo.

**Consequence**

The guard protects against the wrong *settings module*. It does not protect
against a `.env` whose `DATABASE_URL` points somewhere unexpected — `DEBUG` is
true in local settings whatever database they name. **Check where
`DATABASE_URL` points before running this.** That gap is real and was found the
hard way.

### Decision: it writes through the models, not through a service

**Decision**

`seed_demo` uses `Product.objects`, `ProductVariant.objects` and the rest
directly.

**Reason**

[ADR 0002](../decisions/0002-admin-writes-go-through-the-service-layer.md)
constrains `admin.py`, where a merchant's write must go through the service that
owns the rule. There is no catalogue write service to call — `catalog/services.py`
owns stock movement, and nothing here sells anything — and `apps/catalog` owns
these tables.

**Consequence**

If a catalogue write service is ever added, this command should use it, for the
same reason the admin will have to.

### Decision: `seed_orders` does the opposite, and writes through the services

**Decision**

Every seeded order is placed by `place_order` and moved by `mark_order_paid`,
`mark_order_shipped`, `mark_order_delivered`, `cancel_order` and
`complete_cod_payment` — the same functions the admin actions call.

**Reason**

This is the decision above, not a departure from it: its reason was that no
catalogue write service existed, and its consequence said to use one when it did.
For orders every rule lives in a service, and an order invented with
`Order.objects.create` would be a row no checkout could ever produce — a total that
does not match its lines, stock that was never taken, a status reached without its
transition. Seeded data that cannot occur in production is worse than none,
because it is what the admin and the storefront get developed against.

The one exception is the Khalti payment row, written directly.
`initiate_khalti_payment` makes an HTTP request; a seed command must not need
credentials or reach the network. The row's shape is copied from what that service
records, plus what `verify_khalti_payment` adds on a `Completed` lookup.

**Consequence**

Seeding is slower and noisier than inserting rows — every order sends a
confirmation email, and the shipped ones send a notice — and it inherits the
services' failure modes: seeding refuses if the catalogue has too little stock,
rather than quietly creating an order for something that was not there.

### Decision: it is idempotent, and `--flush` is separate

**Decision**

`get_or_create` on every slug. A second run creates nothing. `--flush` deletes
the seeded products first, then seeds.

**Reason**

Re-running a seed is the normal case — after a migration, after a reset, or by
accident. It should be free rather than producing a second set of everything.

**Consequence**

Editing a `ProductSpec` and re-running does **not** update the existing product;
the slug already exists, so it is skipped. Use `--flush` to pick up a change.

### Decision: it seeds the awkward cases deliberately

**Decision**

Nine products including one with no images, one with a single variant, one with
a sparse variant grid, one with a `price_override`, one entirely sold out, and
one unpublished.

**Reason**

A tidy fixture — every product with three images and a full size run — exercises
none of the states that actually break a page. The storefront's variant picker
has to distinguish "sold out" from "never made", its product card has to render
without a photograph, and its visibility scoping has to hide the unpublished one.

**Consequence**

The seeded catalogue looks lopsided, and that is the point. The storefront's own
test fixtures mirror these shapes.

---

## Gotchas

- **`--flush` deletes products, not lookup rows.** `ProductVariant.size` and
  `.color` are `PROTECT`, so a size cannot be deleted while a variant uses it,
  and `get_or_create` makes re-seeding them free anyway.
- **Images are written through the storage backend in use.** Locally that is
  `FileSystemStorage`, so files land in `MEDIA_ROOT` and `image.url` is a
  **relative** path — which is why the storefront resolves image URLs against
  the API base. Against Cloudinary credentials it would upload for real.
- **Each image is saved under a per-product name.** The same source file backs
  several products, and without distinct names the storage backend suffixes the
  collisions and the names drift between runs.
- **The tests point `MEDIA_ROOT` at `tmp_path`**, or seeded images accumulate in
  the repository's own media directory every time the suite runs.
- The SKU prefix is derived from the product's initials, so two products whose
  words start with the same letters would collide on the unique `sku`
  constraint. With nine hand-written products they do not; a tenth needs
  checking.
- The photographs are landscapes and objects, not garments. Crops and tonal
  range are representative; the subject is not.
- **Flush in the order the foreign keys demand: orders, then products.**
  `OrderItem.variant` is `PROTECT`, so once `seed_orders` has run,
  `seed_demo --flush` cannot delete a seeded product. It raises a `CommandError`
  naming `seed_orders --flush` rather than a traceback naming a foreign key, and
  `make reseed` does both in the right order.
- **`seed_orders` prints a wall of email.** Every placement sends a confirmation
  and every shipped order a notice, through `local.py`'s console backend. That is
  the emails working, and the command says so on the last line.
- **An order object handed to a transition service is immediately stale.**
  `complete_cod_payment` and `cancel_order` refetch under `select_for_update()`
  and mutate *that* instance, so the caller's copy keeps its old status and the
  next transition refuses. `seed_orders` calls `refresh_from_db()` between steps
  and counts the final statuses out of the database rather than from the objects.
  Both were live bugs before they were comments.
- **Seeded orders are recognised by their email domain**, `@seed.invalid`. Order
  numbers come from a Postgres sequence and cannot be chosen, so there is nothing
  else stable to match on. `.invalid` is reserved by RFC 2606, so a seeded
  confirmation cannot reach a real inbox even if the seed is pointed at a real
  relay.
- **`--flush` does not return stock.** Deleting an order row is not cancelling an
  order; the units it held stay held. Cancel it first, or reseed the catalogue
  too.

---

## API

None. This feature adds no endpoint.

---

## Data changes

None. No model, field, constraint, index or migration. It writes rows using the
schema `product-catalog.md` defines.

---

## Permissions

None over HTTP. The command runs from a shell with database access, and refuses
to run unless `DEBUG`.

---

## Tests

`apps/catalog/tests/test_seed_demo.py`:

- `test_seeding_outside_debug_is_refused` — and that nothing was written
- `test_seed_populates_the_lookup_tables_a_variant_needs`
- `test_seed_creates_a_one_level_category_tree`
- `test_seed_leaves_one_product_unpublished`
- `test_running_twice_creates_no_duplicates` — the idempotency claim
- `test_flush_removes_the_seeded_products_and_reseeds`
- `test_seed_includes_the_shapes_the_storefront_has_to_survive` — no images, a
  single variant, sold out, a price override
- `test_seed_gives_a_sparse_variant_grid_not_a_cartesian_product`
- `test_every_product_with_images_has_exactly_one_primary`
- `test_seeded_images_do_not_collide_between_products`

`apps/orders/tests/test_seed_orders.py`:

- `test_seeding_outside_debug_is_refused` — and that nothing was written
- `test_seeding_without_a_catalogue_says_which_command_to_run_first`
- `test_seed_covers_every_order_status` — asserted against `OrderStatus.values`,
  so adding a status without seeding one fails here
- `test_every_seeded_order_has_a_payment`
- `test_seed_covers_both_payment_methods_paid_and_unpaid` — all four pairings
- **`test_seed_leaves_one_khalti_order_holding_stock`** — ADR 0004's accepted
  failure mode, which is what the admin's verify action and the handover's daily
  check both exist for. Without it the seed would only show the happy path
- **`test_seed_never_calls_khalti`** — the reason the Khalti payment row is
  written directly
- `test_seeding_takes_stock_for_live_orders_and_gives_it_back_for_cancelled` —
  the catalogue is down by exactly what live orders hold, which only holds if the
  real services did the arithmetic
- `test_flush_removes_the_orders_and_their_payments`
- `test_flush_leaves_the_catalogue_alone`
- `test_flush_only_deletes_without_reseeding` and
  `test_flush_only_releases_the_catalogue_for_reseeding` — the `make reseed`
  sequence. Plain `--flush` reseeds, and those new orders would `PROTECT` the
  catalogue from the very next command, so `reseed` was broken until
  `--flush-only` existed
- `test_seeded_products_cannot_be_flushed_while_orders_reference_them` — the
  `PROTECT` guard, and that the error names the command that releases them

---

## Files

```text
apps/catalog/management/
├── __init__.py
└── commands/
    ├── __init__.py
    ├── seed_demo.py
    └── seed_assets/
        ├── LICENSE.md
        └── shot-01.jpg … shot-12.jpg
apps/catalog/tests/test_seed_demo.py
apps/orders/management/
├── __init__.py
└── commands/
    ├── __init__.py
    └── seed_orders.py              the order history
apps/orders/tests/test_seed_orders.py
Makefile                            the seed and reseed targets
```

---

## Future context

The photographs are placeholders from Lorem Picsum under the Unsplash License,
credited in `seed_assets/LICENSE.md`. They are not the brand's imagery and must
not reach anything a customer sees.

This command exists because of a gap, and the gap is `merchant-admin.md` (#10).
When that lands, re-read this document rather than assuming the command should
stay as it is.

The DEBUG guard is worth understanding precisely: it checks the settings module,
not the database. `config.settings.local` sets `DEBUG = True` whatever
`DATABASE_URL` names, so the guard does not stop a local settings module pointed
at a remote database. Check the connection before running a write command.
