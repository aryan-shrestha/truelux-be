# Skin types and product care details

Status: Implemented

Last updated: 2026-09-26

---

## Goal

The storefront design (`../front-end/docs/design/`) lets customers shop by skin type
from the mega-menu, and shows **Suited to**, **Skin feel** and **Key ingredients**
on every product page. The catalogue has to carry that data. The design's menu also
has a "Shop All" link under each parent category, so filtering by a parent has to
include its children.

---

## Scope

What is included in this implementation?

- `SkinType` lookup model: Normal, Dry, Oily, Combination, Sensitive, Mature
- `Product.skin_types`: many-to-many, optional
- `Product.skin_feel` (short text) and `Product.key_ingredients` (text), both
  optional
- Public `GET /api/v1/skin-types/` facet and a repeatable `?skin_type=` filter
- `?category=<parent>` also matches products in that category's direct children
- Admin API: skin types CRUD; the product write accepts `skin_type_ids`,
  `skin_feel` and `key_ingredients`
- Seed data for all of the above. The category tree is reshaped to match the
  design's menu.

What is explicitly outside the scope?

- Skin-type quizzes or recommendations
- A structured, searchable ingredient list

---

## Context

This follows the lookup-table pattern of `Shade` and `Size`
([ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md)). The category
tree stays one level deep. `catalog-browsing.md` used to record that a parent filter
did not descend; it now records that it does.

---

## Planned

- `SkinType(UUIDModel, TimeStampedModel)`: `name` (unique), `slug` (unique),
  `sort_order`. `db_table = "skin_type"`.
- `Product.skin_types = ManyToManyField(SkinType, blank=True, related_name="products")`.
- `Product.skin_feel = CharField(max_length=200, blank=True)`.
- `Product.key_ingredients = TextField(blank=True)`.
- The detail selector prefetches `skin_types`. The list does not need them.
- `?skin_type=a&skin_type=b` matches either, using `.distinct()`. An unknown slug is
  `400 validation_error`, consistent with `?brand=`.
- `?category=<slug>` matches `category__slug=<slug>` OR `category__parent__slug=<slug>`.
- `/skin-types/` is a facet like `/shades/`: only skin types used by a visible
  product, as a bare array in `sort_order`.
- Admin: `skin-types/` and `skin-types/{id}/` behave like the other taxonomy routes,
  with `product_count`. Deleting a skin type **removes it from products** (M2M), so
  it is not a 409.
- The seed category tree mirrors the design's mega-menu, and every seeded skincare
  and body product gets 1–4 skin types, a `skin_feel` and an INCI-style
  `key_ingredients` line.

---

## Implemented

- `apps/catalog/models.py` — `SkinType` (`name` and `slug` unique, max 50;
  `sort_order`; ordering `["sort_order", "name"]`; `db_table = "skin_type"`).
  `Product.skin_types` (`blank=True`, `related_name="products"`, join table
  `product_skin_types`), `Product.skin_feel` (`max_length=200`, blank) and
  `Product.key_ingredients` (blank `TextField`).
- `apps/catalog/migrations/0002_skin_types.py` — the table, the join table and the
  two columns. No data migration.
- `apps/catalog/selectors.py` — `get_published_product_by_slug` adds `"skin_types"`
  to its prefetches. `list_skin_types_in_use` keeps a skin type only when an
  `Exists` over the join table finds a product that is published and whose brand is
  active, so a skin type used by many products is listed once.
- `apps/catalog/filters.py` — `ProductFilter.skin_type`, a `SlugMultipleChoiceFilter`
  on `skin_types__slug` (django-filter's multiple-choice filters OR the values and
  apply `.distinct()` by default). `ProductFilter.category` is now a method filter,
  `Q(category__slug=value) | Q(category__parent__slug=value)`.
- `apps/catalog/serializers.py` — `SkinTypeSerializer` (`name`, `slug`);
  `ProductDetailSerializer` adds `skin_types`, `skin_feel` and `key_ingredients`.
  List items are unchanged.
- `apps/catalog/views.py`, `urls.py` — `SkinTypeListView` at `skin-types/`
  (`skin-type-list`): `AllowAny`, `catalog` throttle scope, unpaginated.
- `apps/catalog/services/taxonomy.py` — `SkinType` joins the taxonomy writes
  (`name`, `slug`, `sort_order`), so slugs are derived and suffixed like the others.
- `apps/catalog/services/products.py` — `skin_feel` and `key_ingredients` are in
  `PRODUCT_FIELDS`. `create_product` and `update_product` take
  `skin_types: Iterable[SkinType] | None`; when it is not `None` the product row is
  saved and the set replaced in one `transaction.atomic()`. `None` leaves the set
  untouched.
- `apps/backoffice/` — `SkinTypeListView` / `SkinTypeDetailView` on the shared
  taxonomy views (`list_skin_types` annotates `product_count`);
  `ProductWriteSerializer` gains `skin_type_ids` (a many `PrimaryKeyRelatedField`
  with `source="skin_types"`), `skin_feel` and `key_ingredients`;
  `AdminProductDetailSerializer` renders `skin_types` as `[{id, name, slug}]` plus
  the two strings, and `get_product` prefetches them.
- `apps/catalog/admin.py` — `SkinTypeAdmin`; `ProductAdmin` filters by skin type and
  edits the set with `filter_horizontal`.
- Seed data: see `demo-seed.md`.

---

## Remaining

None.

---

## Decisions

### Decision: deleting a skin type detaches it

**Decision**

A skin type in use can be deleted; the join rows go with it (`204`, not `409`).

**Reason**

A skin type is a label on a product, not something a product or an order depends
on. Brands, categories, shades and sizes are `PROTECT` because a product or variant
cannot exist without them; a product without a skin type is valid.

**Consequence**

The admin app should warn before the delete, using `product_count`.

### Decision: the category filter descends one level

**Decision**

`?category=<slug>` matches the category and its direct children.

**Reason**

The design's "Shop All" link under each parent category. The tree is one level deep,
so one `OR` covers it without a recursive query.

**Consequence**

A deeper tree would need this filter rewritten. There is no way to ask for a parent's
own products only.

---

## Gotchas

- `/skin-types/` is a facet, not the lookup table: a skin type used only by an
  unpublished product or an inactive brand's product is not listed. The admin API
  lists every row.
- `?skin_type=` validates slugs against every skin type, so an unknown slug is
  `400 validation_error` while a known-but-unused one returns an empty page.
- `skin_type_ids` replaces the whole set on `PATCH`; omit it to leave the set alone,
  send `[]` to clear it.
- The public detail is now four queries (product, variants, images, skin types).
- The admin product **list** carries none of the three fields; only the admin detail
  and write do.

---

## API

### `GET /api/v1/skin-types/`

Public, `catalog` throttle scope, bare array in `sort_order, name` order.

```json
[{ "name": "Combination", "slug": "combination" }]
```

### Product list filters

```text
GET /api/v1/products/?skin_type=dry&skin_type=oily
GET /api/v1/products/?category=skincare
```

### Product detail adds

```json
"skin_types": [{ "name": "Combination", "slug": "combination" }],
"skin_feel": "Soothed, balanced, refreshed",
"key_ingredients": "Water (Aqua), Hamamelis Virginiana (Witch Hazel) Water, Niacinamide"
```

`skin_types` is `[]` and the two strings are `""` when not set. List items do not
carry these fields.

### Admin

- Product detail and write add `skin_types` (`[{id, name, slug}]`, in `sort_order`)
  and `skin_type_ids` (on write, a list of UUIDs), `skin_feel` (≤ 200 characters),
  and `key_ingredients`. An unknown id is `400 validation_error` naming
  `skin_type_ids`.
- `GET, POST skin-types/`, `PATCH, DELETE skin-types/{id}/`. Items are
  `{id, name, slug, sort_order, product_count}`; `product_count` counts every
  product, published or not. `slug` is optional on write; a duplicate name or slug is
  `409 conflict`; `DELETE` is `204` even when products use it.

---

## Data changes

`skin_type` table, the `product_skin_types` join table, and the `product.skin_feel`
and `product.key_ingredients` columns, in `catalog/0002_skin_types`.

---

## Permissions

Reads are public (`AllowAny`). Writes go through `admin-api` only (`IsAdminUser`).

---

## Tests

- `apps/catalog/tests/test_skin_types.py` — `?skin_type=a&skin_type=b` is the union,
  each product once; an unknown slug is 400; a parent category matches its own and
  its children's products, and a child does not match its siblings; the facet
  excludes unused, unpublished-only and inactive-brand-only skin types and is in
  `sort_order`; the detail payload shape, with `[]`/`""` when unset; list items do
  not carry the fields.
- `apps/catalog/tests/test_api.py::test_product_detail_query_count_is_constant` — now
  four queries.
- `apps/backoffice/tests/test_taxonomy.py` — skin type CRUD with `product_count`,
  duplicate name is 409, deleting a skin type detaches it from products.
- `apps/backoffice/tests/test_products.py` — create with `skin_type_ids` and the two
  strings; a `PATCH` without `skin_type_ids` keeps the set, with a list replaces it,
  with `[]` clears it; an unknown id is 400 and creates nothing.
- `apps/backoffice/tests/test_permissions.py` covers the new routes automatically.
- `apps/catalog/tests/test_seed_demo.py` — the reshaped tree, two published products
  per child category, care details on skincare and body products, and the flush of
  a retired tree.

---

## Files

```text
apps/catalog/{models,selectors,filters,serializers,views,urls,admin}.py
apps/catalog/migrations/0002_skin_types.py
apps/catalog/services/{products,taxonomy}.py
apps/catalog/management/commands/{seed_demo,_seed_catalogue}.py
apps/catalog/tests/test_skin_types.py
apps/backoffice/{selectors,serializers,views,urls}.py
```
