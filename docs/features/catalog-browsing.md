# Catalog browsing

Status: Implemented

Last updated: 2026-09-21

---

## Goal

Let the Next.js storefront list, filter, sort, search, and display products
without authentication — and without leaking anything the merchant has not
published.

---

## Scope

What is included in this implementation?

- `GET /api/v1/products/` — paginated list with filtering and ordering
- `GET /api/v1/products/{slug}/` — detail with variants and images
- `GET /api/v1/categories/` — the category tree for navigation
- Substring search across product name and description
- A dedicated throttle scope, because the global anonymous rate cannot support
  browsing
- Query shapes that hold at a constant number of queries regardless of result count

What is explicitly outside the scope?

- Any write endpoint. The catalogue is admin-only in Phase 1
- Faceted search, fuzzy matching, typo tolerance, or a search engine
- Recommendations or "related products"
- Per-user personalisation of any kind
- Cursor pagination

---

## Context

This is **the only unauthenticated read surface in the system**, and under
[ADR 0003](../decisions/0003-guest-checkout-with-opaque-order-access-tokens.md)
there is no authenticated one. `REST_FRAMEWORK` defaults to `IsAuthenticated`, so
every endpoint here opts out explicitly with `AllowAny`.

That makes two review criteria load-bearing rather than ceremonial:

**Leakage.** Every field on every serializer is visible to the entire internet.
`convention.md` already forbids `fields = "__all__"` for exactly this reason. An
unpublished product, a variant's internal notes, or a cost field appearing here is
a business disclosure, not a bug report.

**Query count.** The product list reaches product → variants → images, three levels
deep. A missing `prefetch_related` is invisible locally and expensive in production,
where every query crosses the network from Render to Supabase.

`product-catalog.md` defines the models and the relations. This document owns the
queryset shapes and the wire format.

`DefaultLimitOffsetPagination` in `apps/core` is already configured globally at 25
per page, maximum 100.

---

## Planned

The intended implementation, retained for the record of intent. Delivered as
described except for the list prefetch, where `prefetch_related("variants",
"images")` became an `Exists` annotation plus `prefetch_related("images")` — see
the decision below:

- `apps/catalog/selectors.py`: `list_published_products` and
  `get_published_product_by_slug`, both scoping to `is_published=True` **inside the
  selector**, with `select_related("category")` and the prefetches already applied.
  These were listed in `product-catalog.md` but deliberately left to this document,
  which owns the prefetch shape and the query-count tests that make them correct;
  shipping them earlier would have meant untested selectors with no caller
- `apps/catalog/filters.py`: `ProductFilter` with `category` (by slug), `size`
  and `color` (also by slug, since [ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md)
  makes both lookup tables rather than char columns), `min_price`, `max_price`,
  and `in_stock`
- `apps/catalog/serializers.py`: `ProductListSerializer` (lean — card data only),
  `ProductDetailSerializer`, `ProductVariantSerializer`, `ProductImageSerializer`,
  `CategorySerializer`
- `apps/catalog/views.py`: read-only viewsets with `AllowAny`, `lookup_field =
  "slug"`, and the catalogue throttle scope
- `rest_framework.filters.SearchFilter` added to the viewset's `filter_backends`
  with `search_fields = ("name", "description")`
- A `catalog` throttle scope in `DEFAULT_THROTTLE_RATES`
- Registration into `api_v1_patterns` in `config/urls.py`

---

## Implemented

- `apps/catalog/selectors.py` — `list_published_products`,
  `get_published_product_by_slug` and `list_category_tree`. Both product selectors
  filter `is_published=True` themselves; the list annotates `in_stock`,
  `select_related("category")`, `prefetch_related("images")` and orders by
  `("sort_order", "-created_at", "pk")`; the detail adds a `Prefetch` of
  `variants` whose inner queryset carries `select_related("size", "color")` and an
  explicit `size__sort_order` ordering
- `apps/catalog/filters.py` — `ProductFilter` (`category`, `size`, `color`,
  `min_price`, `max_price`, `in_stock`) and `DeterministicOrderingFilter`
- `apps/catalog/serializers.py` — `SizeSerializer`, `ColorSerializer`,
  `CategorySerializer`, `CategoryTreeSerializer`, `ProductImageSerializer`,
  `ProductVariantSerializer`, `ProductListSerializer`, and
  `ProductDetailSerializer` (which extends the list serializer, so the two cannot
  drift). Every `fields` is an explicit tuple and none contains `stock_quantity`
- `apps/catalog/views.py` — `ProductViewSet` (`ReadOnlyModelViewSet`, `AllowAny`,
  `lookup_field = "slug"`, `catalog` throttle scope, filter/search/ordering
  backends) and `CategoryListView` (`ListAPIView`, unpaginated)
- `apps/catalog/urls.py` — a `SimpleRouter` registration for `products` plus the
  `categories/` path, included into `api_v1_patterns` in `config/urls.py`
- `config/settings/base.py` — the `catalog` throttle scope at `600/hour`, from
  `DJANGO_THROTTLE_CATALOG`; `config/settings/test.py` carries its own entry
  because its `DEFAULT_THROTTLE_RATES` override replaces the dict rather than
  merging into it
- `apps/core/throttling.py` — `ResilientScopedRateThrottle`, so the catalogue
  degrades to per-process counting like every other endpoint when Redis is down
- `apps/core/exceptions.py` — an `ObjectDoesNotExist` branch returning 404
  `not_found`. See the decision below
- `apps/catalog/tests/test_api.py` — 21 tests, including the query-count
  assertions at two dataset sizes

---

## Remaining

- **`?category=` matches one category exactly and does not descend into its
  children.** Filtering by a parent category returns only products attached
  directly to it. `Category.parent` allows one level, so the fix is a single
  `Q(category__slug=value) | Q(category__parent__slug=value)`; it is not here
  because nothing has asked for it, and guessing wrong would be a silent change
  to a published filter's meaning later.
- Product-level `in_stock` answers "any variant has stock". A product whose only
  in-stock variant is a size the customer does not wear still reads as in stock;
  narrowing that is what `?size=` combined with `?in_stock=` is for.

---

## Decisions

### Decision: a dedicated `catalog` throttle scope

**Decision**

Catalogue endpoints use `ScopedRateThrottle` with a `catalog` scope, set high.
The global `anon` rate stays at `60/hour`.

The rate is **`600/hour`**, read from `DJANGO_THROTTLE_CATALOG`. Roughly ten
requests a minute per IP: enough for a browsing session that opens a dozen
products, low enough to be worth having. The figure was chosen here rather than
measured, and is the first thing to raise if real traffic trips it.

Declaring `throttle_classes` on the views replaces the global default pair, so a
catalogue request is counted **only** against `catalog` and never against `anon`.
That is deliberate — a storefront session must not spend the budget that protects
the order-number lookup — and it is what
`test_the_catalog_scope_is_separate_from_the_global_anonymous_rate` pins.

**Reason**

A single storefront session fires a list request, several detail requests, and a
category request. `60/hour` per IP exhausts during normal browsing, and behind
carrier-grade NAT an entire neighbourhood shares one address.

The global `anon` rate is not raised to compensate, because it is what protects
every *other* anonymous endpoint — including the order-number lookup, which is an
enumeration surface that specifically benefits from a low ceiling.

**Consequence**

Two rates exist and their purposes differ. Raising `anon` to "fix browsing" would
silently weaken the order lookup. Note this where the rate is defined.

### Decision: visibility is scoped in the selector, not in the view

**Decision**

`is_published=True` is applied inside the selector.

**Reason**

`convention.md`'s rule: filtering in the selector is what makes a hidden object
return 404 rather than 403, and it means a forgotten permission class cannot leak
rows. A `get_queryset` that filters inline is a permission bug waiting to happen.

**Consequence**

There is no code path that can return an unpublished product, including a direct
fetch by slug. A future admin preview feature must add a **separate** selector
rather than parameterising this one.

### Decision: search is `icontains`, not full-text

**Decision**

DRF's `SearchFilter` over `name` and `description`.

**Reason**

The catalogue is a few hundred products. Postgres full-text search, trigram
similarity, or an external engine would each cost setup, an index, and a migration
to solve a problem that does not exist at this size.

**Consequence**

No typo tolerance, no ranking, no stemming. A customer searching "tshirt" does not
find "t-shirt". Revisit when the catalogue passes roughly a thousand products or
when search analytics show misses — `pg_trgm` is the next step, not Elasticsearch.

### Decision: `in_stock` is an annotation, not a variant prefetch

**Decision**

`list_published_products` annotates
`in_stock=Exists(ProductVariant.objects.filter(product=OuterRef("pk"), stock_quantity__gt=0))`.
The list endpoint prefetches `images` only; it does **not** prefetch `variants`.
The `in_stock` filter reads the annotation.

This replaces the `prefetch_related("variants", "images")` this document
originally planned for the list.

**Reason**

The card needs one boolean. Prefetching variants to derive it pulls every variant
of every product on the page — fifteen rows for a garment in five sizes and three
colours — across the network from Render to Supabase, to answer a question
Postgres can answer with a subquery. It also means `stock_quantity` values leave
the database on a request that must never publish them; keeping them in the
subquery is one fewer place for that to go wrong.

The filter benefits twice over: `variants__stock_quantity__gt=0` is a join that
returns a product once per matching variant and needs `.distinct()` to compensate,
while the annotation cannot duplicate a row at all.

**Consequence**

The list is three queries — count, page, images — and stays three at any page
size. The detail endpoint still prefetches variants, because it renders them.

`?size=` and `?color=` remain joins and still carry `.distinct()`; only `in_stock`
escaped. Anything added later that reads variant *data* on the list — a price
range across variants, a colour swatch row — needs the prefetch back, and a
query-count test to go with it.

### Decision: the category tree is one level deep and unpaginated

**Decision**

`GET /api/v1/categories/` returns root categories only, each with a `children`
array, as a bare JSON array with no pagination envelope. `CategoryListView` sets
`pagination_class = None`.

**Reason**

`Category.parent` allows one level, so the response shape mirrors the data model
exactly. Navigation is the only consumer, and it needs the whole tree: paginated
at 25, a merchant adding a 26th root category would watch it vanish from the
storefront menu with nothing failing anywhere. The tree is a few dozen rows.

**Consequence**

This is the one endpoint in the repository that overrides the global pagination
class, which `convention.md` asks to be justified in the feature document — this
is that justification. It also means the response is an array, not an object, so a
client written against the product list's envelope will not read it unchanged.

If categories ever grow past a few hundred rows, this is the endpoint to revisit.

### Decision: a missing row returns 404 from the exception handler

**Decision**

`api_exception_handler` maps `django.core.exceptions.ObjectDoesNotExist` to a 404
with code `not_found`. `get_published_product_by_slug` lets `DoesNotExist`
propagate rather than catching it.

**Reason**

`convention.md` already told selectors to do exactly this — *"do not catch
`DoesNotExist` — let it propagate; the exception handler returns 404"* — but the
handler had no such branch, because until this feature no selector had an HTTP
caller. A propagating `DoesNotExist` reached the unhandled path and would have
returned **500** on every unknown slug.

**Consequence**

The rule now holds for every selector, which matters most for `orders`: ADR 0003
requires a wrong access token to be indistinguishable from a missing order, and
that is exactly what a scoped selector plus this branch produces.

The message is DRF's flat "Not found." — Django's own
`"Product matching query does not exist."` is discarded, so the model name does
not leak.

This is a change to `api-error-contract`'s module, recorded there too.

---

## Gotchas

- **The list endpoint is three queries and must stay three.** Without the
  annotation and the image prefetch, twenty-five products produce fifty extra
  queries, each a network round trip to Supabase. Query-count tests exist to catch
  this regression, not to document current behaviour — and they run at two dataset
  sizes, because a single fixed count passes by accident.
- **`in_stock` is an annotation on the list, not a prefetched relation.** Reading
  `product.variants.all()` from `ProductListSerializer` would be an N+1 that no
  current test would catch as a *count* change, because the count is asserted per
  request, not per row. Add the prefetch back if the list ever renders variant
  data, and change the expected count in the same commit.
- `.iterator()` does not stream here. Server-side cursors are disabled under
  Supabase's pooler, so it still materialises everything. Paginate in
  application code.
- Pagination without an explicit `.order_by()` returns inconsistent pages, and
  Postgres will not warn you. `Product.Meta.ordering` covers the default; any
  custom ordering must still be deterministic — add a tiebreaker on `pk` when
  ordering by a non-unique column such as price.
- **`is_published` is not privacy.** Cloudinary delivery URLs are public and
  permanent, so an unpublished product's images are fetchable by anyone holding a
  URL. The flag controls API visibility only.
- **`?size=` and `?color=` join `variants` and duplicate product rows.** A product
  sold in M across three colours matches `?size=m` three times, so
  `ProductFilter.filter_by_variant` applies `.distinct()`. `?in_stock=` reads the
  annotation instead and needs none — the asymmetry is deliberate, not an
  oversight.
- **Size and colour are joins now, not columns.** `ProductVariant.size` and
  `.color` are foreign keys, so serialising a variant's size reaches a third
  table. `prefetch_related("variants__size", "variants__color")` — or a
  `Prefetch` with `select_related` on the inner queryset — is what keeps the
  query count flat. `ProductVariant` has no `Meta.ordering`, so order variants
  explicitly by `size__sort_order` where they are rendered.
- Detail lookup is by `slug`, not UUID. `convention.md` says detail lookups are by
  UUID; slugs are the deliberate exception here because the storefront needs
  readable, SEO-stable URLs. Stated so it does not read as an oversight.
- **`ProductViewSet.get_object` is overridden**, because the default would build
  the detail response from the *list* queryset, which has no variant prefetch —
  an N+1 that the list's own query-count test cannot see. It calls
  `check_object_permissions` as DRF's implementation does, even though
  `AllowAny` makes that a no-op today.
- **`DeterministicOrderingFilter` appends `pk` to any client ordering.**
  `?ordering=base_price` over a column where a hundred garments share one price
  otherwise returns rows on page 2 that were already on page 1 — Postgres is free
  to order ties differently per query and will not warn. The selector's own
  `.order_by()` already ends in `pk` for the same reason.
- **`ordering_fields` holds only local columns, and must keep to them.** `?size=`
  applies `.distinct()`, and PostgreSQL rejects `SELECT DISTINCT` ordered by an
  expression that is not in the select list. Adding `category__name` to
  `ordering_fields` would therefore 500 on `?size=m&ordering=category__name` while
  working perfectly on either parameter alone. Local columns are all selected, so
  the current set is safe.
- **`SimpleRouter`, not `DefaultRouter`.** The latter adds an API-root view at
  `/api/v1/`, which this document does not publish.
- **Route names are namespaced.** `NamespaceVersioning` puts these under `v1`, so
  it is `reverse("v1:product-list")`, not `reverse("product-list")`.
  `convention.md`'s unprefixed examples predate any registered route.
- Categories are served by a `ListAPIView` rather than a viewset, so that no
  undocumented `categories/{id}/` detail route exists.
- `primary_image` falls back to the first image by `sort_order` when no image is
  flagged primary, so a merchant who forgets the checkbox gets a card with a photo
  rather than a card with a hole. It reads the prefetched images and issues no
  query.

---

## API

### Endpoint

```text
GET /api/v1/products/
GET /api/v1/products/{slug}/
GET /api/v1/categories/
```

### Request

```text
GET /api/v1/products/?category=shirts&size=M&in_stock=true&ordering=-created_at&limit=25&offset=0
GET /api/v1/products/?search=linen
```

### Response

```json
{
  "count": 42,
  "next": "...",
  "previous": null,
  "results": [
    {
      "id": "...",
      "name": "Linen Shirt",
      "slug": "linen-shirt",
      "base_price": "4500.00",
      "category": { "name": "Shirts", "slug": "shirts" },
      "primary_image": { "url": "...", "alt_text": "..." },
      "in_stock": true
    }
  ]
}
```

Detail adds `description`, the full ordered `images` array, and `variants` with
`id`, `size`, `color`, `price`, and `in_stock`. `size` and `color` are objects of
`{name, slug}` — the slug is what `?size=` and `?color=` take, so the client that
renders a picker already holds the value it must send back. `price` is the
variant's resolved price, `price_override` falling through to the product's
`base_price`, as a string like `base_price`.

`GET /api/v1/categories/` returns a bare array with no pagination envelope:

```json
[
  { "name": "Shirts", "slug": "shirts", "children": [{ "name": "Linen", "slug": "linen" }] },
  { "name": "Trousers", "slug": "trousers", "children": [] }
]
```

### Errors

```json
{ "error": { "code": "not_found", "message": "Not found.", "details": {} } }
```

An unpublished or non-existent slug returns the same 404. Throttling returns 429
with code `throttled`.

**`stock_quantity` is never serialised.** Variants expose a boolean `in_stock`, not
a number — exact inventory levels are commercially sensitive and competitors read
public APIs.

---

## Data changes

None. Models are defined in `product-catalog.md`.

---

## Permissions

`AllowAny` on every endpoint, declared explicitly on each view even though the
consequence is an open endpoint — precisely because the consequence is an open
endpoint.

Read-only by construction: these are `ReadOnlyModelViewSet`, so no HTTP verb other
than `GET` is routed.

Visibility is enforced in the selector, so there is no object-level permission
class here. There is nothing to own.

---

## Tests

All in `apps/catalog/tests/test_api.py` unless noted.

- `test_product_list_returns_200_for_anonymous_user`
- `test_product_list_excludes_unpublished_products`
- `test_product_detail_returns_variants_and_images`
- `test_product_detail_for_unpublished_slug_returns_404`
- `test_product_detail_for_unknown_slug_returns_404` — the same response as the
  unpublished case, so the API does not confirm that a hidden slug exists
- `test_product_list_query_count_is_constant` — `django_assert_num_queries(3)`,
  parametrised over five and then twenty products
- `test_product_detail_query_count_is_constant` — `django_assert_num_queries(3)`,
  parametrised over two and then six variants. This is the one that catches a
  regression in the size/colour `select_related` that ADR 0007 made necessary
- `test_product_serializer_does_not_expose_stock_quantity` — list and detail
- `test_filter_by_size_returns_only_matching_products`
- `test_filter_by_size_does_not_duplicate_a_product_sold_in_several_colours`
- `test_in_stock_filter_does_not_duplicate_rows`
- `test_filter_by_category_and_price_range`
- `test_search_matches_name_and_description`
- `test_ordering_by_price_paginates_without_repeating_rows` — four products at one
  price across two pages, the `pk` tiebreaker
- `test_variants_are_ordered_by_size_sort_order`
- `test_category_list_returns_roots_with_their_children`
- `test_write_methods_are_not_routed` — 405, the read-only surface
- `test_exceeding_catalog_throttle_returns_429_with_throttled_code`
- `test_the_catalog_scope_is_separate_from_the_global_anonymous_rate`
- `apps/core/tests/test_exceptions.py::test_a_missing_object_maps_to_404_so_selectors_need_not_catch_it`
- `apps/core/tests/test_exceptions.py::test_a_missing_object_response_carries_no_lookup_detail`

Two testing notes worth keeping:

- `DEFAULT_THROTTLE_RATES` is read onto `SimpleRateThrottle.THROTTLE_RATES` at
  import, so the `settings` fixture cannot change a rate. The throttle tests patch
  that class attribute instead.
- `ProductFactory` leaves `is_published` at its model default of `False`. Every
  test that expects a product to be visible passes `is_published=True` explicitly,
  per `convention.md`'s rule about not depending on factory defaults.

---

## Files

```text
apps/catalog/
├── selectors.py
├── filters.py
├── serializers.py
├── views.py
├── urls.py
└── tests/
    └── test_api.py
apps/core/throttling.py          ResilientScopedRateThrottle
apps/core/exceptions.py          the ObjectDoesNotExist branch
config/urls.py                   api_v1_patterns
config/settings/base.py          the catalog throttle rate
.env.example                     DJANGO_THROTTLE_CATALOG
config/settings/test.py          its own catalog rate
pyproject.toml                   mypy override for django_filters
```

`django-filter` ships neither type hints nor a stub package, so the first typed
import of it fails `mypy --strict`. The `ignore_missing_imports` override handles
the import; `ProductFilter` additionally carries a `# type: ignore[misc]` because
subclassing an implicitly-`Any` base is its own strict-mode error.

---

## Future context

The query-count tests are the most valuable tests in this document. They are the
only thing standing between a serializer change and a production N+1 that nobody
notices until Supabase egress or latency spikes. Assert against two different
dataset sizes — a single fixed count passes accidentally.

Two things here are deliberate exceptions to repository conventions, both stated
above so they are not "fixed" later: slug lookups instead of UUID, and a second
throttle scope alongside the global anonymous one.

When Phase 2 adds discounts, `base_price` stays the list price and the discounted
figure becomes an additional serialized field. Overwriting `base_price` would make
order history unreadable.
