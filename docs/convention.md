# Code Conventions

Last updated: 2026-09-20

This document records conventions that apply across the repository.

Prefer existing code examples over adding rules here. Only record conventions
that future contributors or agents need to know.

See [architecture.md](architecture.md) for layer responsibilities and system
constraints. This file covers how the code is written, not how it is arranged.

---

## Naming

### Files

`snake_case.py`. One concern per module, named for the concern.

```text
apps/orders/services.py          write operations
apps/orders/selectors.py         read operations
apps/orders/exceptions.py        domain exceptions
apps/orders/filters.py           FilterSet classes
apps/orders/tests/factories.py
apps/orders/tests/test_services.py
apps/orders/tests/test_api.py
```

No `utils.py`, `helpers.py`, or `common.py`. A module whose name does not say what
is inside becomes a dumping ground within a month. If a helper has no obvious home,
it usually belongs next to its only caller.

Split a module when it grows past roughly 400 lines, into `services/` with
`__init__.py` re-exporting the public names, so imports elsewhere do not change.

### Classes

`PascalCase`, with a suffix that identifies the kind:

```python
class Order(models.Model): ...


class OrderCreateSerializer(serializers.Serializer): ...


class OrderViewSet(viewsets.ModelViewSet): ...


class OrderFilter(django_filters.FilterSet): ...


class IsOrderOwner(BasePermission): ...


class OrderAlreadyShipped(DomainError): ...


class OrderFactory(factory.django.DjangoModelFactory): ...
```

Models are singular (`Order`, not `Orders`). Permissions read as a predicate
(`IsOwnerOrAdmin`, `CanRefund`). Exceptions name the condition, not the remedy
(`InsufficientStock`, not `StockCheckFailed`), and subclass `DomainError`.

### Functions

Services are imperative verb phrases. Selectors start with `get_` for one object or
`list_` for many.

```python
def create_order(...) -> Order: ...
def cancel_order(...) -> Order: ...

def get_order(...) -> Order: ...
def list_orders_for_user(...) -> QuerySet[Order]: ...
```

Predicates read as questions: `is_active`, `has_shipped`, `can_be_cancelled`.
Module-private helpers take a leading underscore. `handle_`, `process_`, `manage_`,
and `do_` say nothing — name the actual operation.

### Variables

`snake_case`. Collections are plural, single objects singular. Name the content, not
the container: `orders`, not `order_list`, `data`, `result`, or `info`.

Booleans read as assertions: `is_paid`, `has_items`, `should_notify`. Avoid negated
names — `is_hidden` beats `is_not_visible`, which produces `if not is_not_visible`.

Single letters only as comprehension or loop variables over an obvious collection.
`qs` and `pk` are accepted; invent no other abbreviations.

Module constants are `UPPER_SNAKE_CASE` and live at the top of the module that uses
them. A literal used twice becomes a constant; a literal used once stays inline.

---

## Django apps

App packages live under `apps/`, named as a lowercase plural noun for the thing they
own: `users`, `orders`, `payments`. A collective noun is allowed when an app owns a
cluster of related tables that no single plural describes — `catalog` owns
categories, products, variants, and images, and calling it `products` would misname
two thirds of it. The `AppConfig` carries the full dotted path:

```python
class OrdersConfig(AppConfig):
    name = "apps.orders"
    label = "orders"
```

Each app owns its models, endpoints, and the rules for changing its data. An app is
worth creating when it owns tables no other app writes to; otherwise the code
belongs in an existing app.

**Shared code goes in `apps/core`**, and only infrastructure: base models,
pagination, permissions, the exception handler, the base `DomainError`. `core` never
imports from a domain app. If something in `core` would need to know what an
`Order` is, it is not shared code.

**Cross-app access goes through the owning app's service or selector**, never
through its models or querysets directly:

```python
from apps.orders.selectors import get_order  # yes
from apps.orders.models import Order  # only inside apps/orders
```

The exception is `ForeignKey` targets, which necessarily import the model.

---

## Services

Service functions should:

- take keyword-only arguments, so call sites are readable and argument order is not
  part of the contract
- be fully type-annotated, including the return type
- own their transaction boundary with an explicit `transaction.atomic()`
- raise a `DomainError` subclass when a business rule rejects the request
- return the model instance or plain data they produced
- perform external calls (Cloudinary) **before** opening a transaction

Services should not:

- receive request objects
- receive serializers
- return `Response`, status codes, or anything HTTP-shaped
- be called by another service through the ORM instead of its service function
- validate input shape — the serializer did that

```python
def create_order(*, user: User, product_id: UUID, quantity: int) -> Order:
    if quantity < 1:
        raise InvalidQuantity(details={"quantity": quantity})

    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        if product.stock < quantity:
            raise InsufficientStock(details={"available": product.stock})

        product.stock -= quantity
        product.save(update_fields=["stock", "updated_at"])

        return Order.objects.create(user=user, product=product, quantity=quantity)
```

Note the row lock: reading stock and decrementing it without `select_for_update()`
lets two concurrent requests both pass the check. Any read-then-write on a shared
counter needs the lock or a database constraint.

Uniqueness is enforced by the database, and the service translates the failure:

```python
try:
    return User.objects.create_user(email=email, password=password)
except IntegrityError as exc:
    raise EmailAlreadyRegistered from exc
```

Checking `User.objects.filter(email=email).exists()` first is a race, not a
validation.

---

## Selectors

Selectors should:

- take keyword-only arguments, starting with the caller (`user`) when the result is
  scoped to them
- apply visibility rules themselves, so no caller can forget them
- return a fully-shaped queryset — joins and prefetches already applied
- annotate aggregates rather than letting the serializer compute them per row

Selectors should not:

- write anything, including `get_or_create` or `update`
- accept a request or serializer
- return a lazy queryset that the serializer then triggers extra queries on
- catch `DoesNotExist` — let it propagate; the exception handler returns 404

```python
def get_order_for_user(*, user: User, order_id: UUID) -> Order:
    return Order.objects.select_related("product").get(pk=order_id, user=user)


def list_orders_for_user(*, user: User) -> QuerySet[Order]:
    return Order.objects.filter(user=user).select_related("product").order_by("-created_at")
```

Filtering by `user=user` inside the selector is what makes a missing object return
404 rather than 403, and it is why a forgotten permission class cannot leak rows.

---

## Serializers

**Separate serializers per direction and per action.** One serializer carrying six
`read_only` flags and three conditional branches is harder to read than three small
ones.

```python
class OrderCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class OrderReadSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ("id", "product", "quantity", "status", "created_at")
```

Conventions:

- `fields` is always an explicit tuple. Never `__all__` — it leaks every column you
  add later, including ones you did not mean to publish.
- Input serializers are plain `Serializer` when they feed a service; `ModelSerializer`
  is for output, where mirroring the model is the point.
- Nested serializers are read-only. Writes take identifiers
  (`product_id = serializers.UUIDField()`), and the service resolves them.
- `validate_<field>` for one field, `validate` for rules spanning fields. Both are
  for _shape_; anything requiring a query or a business rule belongs in the service.
- `SerializerMethodField` must not query. If it needs data, the selector should have
  annotated or prefetched it.

```python
class DateRangeSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if attrs["start"] > attrs["end"]:
            raise serializers.ValidationError({"end": "Must be on or after start."})
        return attrs
```

Validation errors are raised as a dict keyed by field, so the error envelope's
`details` names the offending field.

---

## Views

**`ModelViewSet` for a resource with standard CRUD; `APIView` for anything else.**
A viewset with four overridden methods and two `@action`s should have been an
`APIView`.

```python
class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, IsOwnerOrAdmin)
    filterset_class = OrderFilter

    def get_queryset(self):
        return list_orders_for_user(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_order(user=request.user, **serializer.validated_data)
        return Response(OrderReadSerializer(order).data, status=HTTP_201_CREATED)
```

Conventions:

- `permission_classes` is declared on every view, even when it matches the global
  default. Explicit beats inherited when the consequence is an open endpoint.
- `get_queryset` delegates to a selector. A queryset built inline in a view is a
  permission bug waiting to happen.
- Always `raise_exception=True`; never inspect `serializer.errors` by hand.
- Responses are built from a read serializer, so create and retrieve return the same
  shape.
- Status codes: 200 read and update, 201 create, 204 delete with an empty body.
- Pagination comes from the global default class. Override `pagination_class` only
  where a genuinely different page size is required, and say why in the feature doc.
- No `try`/`except` around service calls. Domain exceptions are the handler's job.

---

## Errors

Domain exceptions subclass a single base in `apps/core/exceptions.py` and carry a
stable machine-readable `code`:

```python
class DomainError(Exception):
    code = "domain_error"
    message = "The request could not be completed."
    status_code = 422

    def __init__(self, *, message: str | None = None, details: dict | None = None):
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)
```

Per-domain subclasses live in `apps/<domain>/exceptions.py`:

```python
class InsufficientStock(DomainError):
    code = "insufficient_stock"
    message = "Not enough stock to fulfil this order."
```

Conventions:

- **Raise, never return.** A service returning `(None, "error")` forces every caller
  to remember to check, and one eventually will not.
- `code` is part of the public API. Clients branch on it, so renaming one is a
  breaking change. `message` is for humans and may be reworded freely.
- Codes are `snake_case` and describe the condition, not the HTTP status.
- `details` carries structured context for the client — the offending field, the
  available quantity. Never an exception string or a stack trace.
- Catch an exception only to add context, then re-raise with `from exc`. A bare
  `except Exception: pass` is never correct here.

The envelope and the status code table are in
[architecture.md](architecture.md#error-handling). Do not duplicate them; a second
copy will drift.

---

## Permissions

`IsAuthenticated` is the project-wide default in `REST_FRAMEWORK`, so a new endpoint
is private until someone opts out. Public endpoints declare
`permission_classes = (AllowAny,)` explicitly.

Object-level ownership uses one reusable class in `apps/core/permissions.py`:

```python
class IsOwnerOrAdmin(BasePermission):
    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return bool(getattr(obj, self.owner_field) == request.user)
```

Conventions:

- Names read as predicates: `IsOwnerOrAdmin`, `IsStaff`, `CanRefundOrder`.
- **Never check ownership inline in a view.** `if obj.user != request.user` scattered
  across views is unauditable; a permission class is greppable.
- Ownership is enforced twice by design — the selector scopes the queryset, the
  permission class guards the object. Neither is redundant: the first protects
  lists, the second protects direct fetches by ID.
- `owner_field` exists so a model whose owner is not called `user` can reuse the
  class. Subclass and override it; do not write a second permission class.
- Permissions answer _may this caller do this_. They never answer _is this data
  valid_ or _is this state allowed_ — those are the service's job.
- Django model permissions and groups are used only by the admin, not by the API.

---

## Querying

All querying lives in selectors. These conventions apply there.

```python
Order.objects.select_related("user", "product")  # FK / OneToOne, forward
Order.objects.prefetch_related("items")  # reverse FK / M2M
```

- Add `select_related` for every forward relation the serializer touches. A missing
  one is invisible locally and expensive in production, where each query crosses the
  network to Supabase.
- `prefetch_related` for reverse and many-to-many relations. Use `Prefetch` when the
  inner set needs its own filter or ordering.
- Aggregate with `annotate`, never in Python:

```python
.annotate(item_count=Count("items"))
```

- `.exists()` to test presence, `.count()` to count. Never `len(qs)` or `if qs:`
  for either — both pull every row.
- Always `.order_by()` explicitly on anything paginated. Unordered pagination gives
  inconsistent pages, and Postgres will not warn you.
- Use `update_fields` on `.save()` when writing a subset of columns.
- `.only()` / `.defer()` only with a measurement that justifies them. They cause
  extra queries when something later touches a deferred field.
- **`.iterator()` does not stream** — server-side cursors are disabled under
  Supabase's pooler, so it still materialises everything. Paginate large
  reads in application code instead.

Request-driven filtering is a `FilterSet` in `filters.py`, never hand-parsed query
parameters:

```python
class OrderFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    created_after = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")

    class Meta:
        model = Order
        fields = ("status", "created_after")
```

---

## Testing

`pytest` with `pytest-django`. Every test that touches the database is marked
`@pytest.mark.django_db`.

### Factories

`factory_boy`, one factory per model, in `apps/<domain>/tests/factories.py`, named
`<Model>Factory`.

```python
class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = 1
```

- Factories set only what the model requires. Anything a test asserts on, the test
  passes in explicitly — a test that depends on a factory default breaks when the
  default changes, for reasons that look unrelated.
- `Sequence` for unique fields. Random data makes failures unreproducible.
- `SubFactory` for relations; `build()` when no database row is needed.
- Variants go in `class Params` traits, not in separate `ShippedOrderFactory`
  classes.

### Fixtures

Pytest fixtures for shared setup only: the API client, an authenticated client,
frozen time. Never JSON fixture files — they drift from the models silently and no
migration updates them.

```python
@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client
```

A fixture used by one test file lives in that file; shared ones go in the nearest
`conftest.py`.

### API tests

Tests hit the URL through `reverse()`, never a hardcoded path.

```python
def test_create_order_returns_201(auth_client, product):
    url = reverse("order-list")

    response = auth_client.post(url, {"product_id": str(product.id), "quantity": 2})

    assert response.status_code == 201
    assert response.data["quantity"] == 2
```

Every endpoint has at least: the happy path, the anonymous case (401), the
wrong-owner case (404), and one validation failure (400 with the expected `code`).
`force_authenticate` for authentication in tests — do not log in through the token
endpoint unless the token endpoint is what you are testing.

### Assertions

- Assert on the specific fields that matter, not `response.data == {...}`. Whole-dict
  equality turns every added field into a failing test.
- Assert the error `code`, not the message. Messages are meant to be reworded.
- Assert query counts where an N+1 would be a regression:

```python
def test_order_list_is_constant_queries(auth_client, django_assert_num_queries):
    OrderFactory.create_batch(5, user=...)

    with django_assert_num_queries(3):
        auth_client.get(reverse("order-list"))
```

- Three blank-line-separated blocks per test: arrange, act, assert. Do not label them
  with comments; the shape is the label.
- Test names state the condition and the expectation:
  `test_cancel_order_after_shipping_returns_422`.

---

## Formatting and linting

`ruff` for both linting and formatting; `ruff format` is authoritative and its
output is never hand-adjusted. Line length 100.

Repository-specific rules beyond the tooling config:

- **Absolute imports only.** `from apps.orders.services import create_order`. Relative
  imports hide which app you are in when a file is moved.
- No wildcard imports, including in `__init__.py`. Re-export explicitly.
- Import the module for Django internals (`from django.db import transaction`, then
  `transaction.atomic()`), so the call site says where the behaviour comes from.
- f-strings for interpolation, except in logging calls (see Logging).
- Trailing commas in every multi-line collection and signature, so diffs show one
  changed line.
- A `# noqa` needs the specific rule code and a reason on the same line:
  `# noqa: E501 - URL from the provider, cannot be wrapped`. A bare `# noqa` is
  rejected in review.

---

## Type checking

`mypy` with `django-stubs` and `djangorestframework-stubs`, configured in
`pyproject.toml`. **`strict = true` applies to the whole repository**, with
`tests.*` and `apps.*.tests.*` relaxed by an existing override so factories and
test helpers need no annotations.

Consequences that follow from strict mode, rather than from taste:

- **Everything outside tests is fully annotated**, including views and serializers.
  Leaving a view method unannotated fails `make typecheck`; it is not a style
  preference.
- **Services and selectors especially.** They are the layer other code calls, and
  the signature is the contract.
- `QuerySet[Model]` as the return type for list selectors, not `list` or `Any`.

```python
def list_orders_for_user(*, user: User) -> QuerySet[Order]: ...
def get_order_for_user(*, user: User, order_id: UUID) -> Order: ...
def cancel_order(*, order: Order) -> Order: ...
```

- `X | None` over `Optional[X]`.
- The user model is typed as the concrete class via
  `from apps.users.models import User`, not `AbstractBaseUser` or
  `settings.AUTH_USER_MODEL`.
- `# type: ignore` always names the error code and the reason. The reason follows a
  second `#`, because mypy rejects anything else after the bracket as an invalid
  comment:
  `# type: ignore[attr-defined]  # django-stubs misses the related manager here`.
  Bare ignores and `Any` as a way out of a hard signature are rejected in review.

---

## Logging

`structlog`, via the project's own helper. One logger per module, named by module:

```python
from apps.core.logging import get_logger

logger = get_logger(__name__)
```

Never `logging.getLogger`, never `getLogger("app")`, never a custom string.
`__name__` makes the source greppable and lets levels be configured per package,
and `get_logger` is what binds the request id from `RequestIDMiddleware` into every
line. The stdlib logger does not, which is why every log call must go through the
helper.

The event name is a dotted, lowercase, past-tense identifier. Context is passed as
keyword arguments — never interpolated, never `extra={...}` — so the event stays a
single searchable token and the fields stay queryable:

```python
logger.info("order.created", order_id=order.id, item_count=len(items))
```

Levels:

| Level     | Use                                                                      |
| --------- | ------------------------------------------------------------------------ |
| `DEBUG`   | Local diagnosis. Never enabled in production.                            |
| `INFO`    | A state change worth reconstructing later: created, cancelled, refunded. |
| `WARNING` | Expected but notable: an external call retried, a rate limit hit.        |
| `ERROR`   | A human needs to look. Unhandled exceptions, failed external writes.     |

- Validation failures and permission denials are **not** errors. They are the system
  working. Logging them at `ERROR` makes the error log useless.
- No `CRITICAL`; nothing here distinguishes it from `ERROR`.
- Log at the service layer, where the state change happens — not in views, where you
  would log the same event once per endpoint that triggers it.

**Never logged, at any level:** passwords, raw request bodies, JWTs or any
`Authorization` header, `DATABASE_URL` or any connection string, Cloudinary API
secrets and signatures, password-reset tokens, and full email addresses. Log
`user_id` instead of `email`. Exception objects may be logged; request payloads that
produced them may not.

Every log line carries the request id from the middleware, so a client-reported
failure can be traced in Render's logs.

---

## Comments and docstrings

The default is no comment and no obvious docstring (see `CLAUDE.md`). The exceptions:

- **A docstring on a service that raises**, listing what it raises, because callers
  cannot see that from the signature:

```python
def cancel_order(*, order: Order) -> Order:
    """Raises OrderAlreadyShipped if the order has left the warehouse."""
```

- **`RunPython` in a migration** gets a comment explaining what the data looked like
  before, since the migration outlives the context that produced it.
- **`# noqa` and `# type: ignore`** carry a rule code and a reason.
- **A non-obvious lock, ordering, or external-API workaround** gets a why-comment, as
  in `create_order` above.

Everything else — narrating a line, restating a signature, sectioning a file with
banner comments — is removed in review.

---

## Other conventions

**URLs.** Lowercase, plural nouns, hyphens between words, trailing slash, versioned
prefix: `/api/v1/orders/`, `/api/v1/orders/{id}/cancel/`. Detail lookups are by UUID.
Nesting stops at one level; anything deeper becomes a filter
(`/api/v1/items/?order=<id>`).

**Router names.** Registered as the plural resource, giving `order-list` and
`order-detail` for `reverse()`.

**Settings.** Read every environment variable in `config/settings/base.py` and
nowhere else, so one file lists the entire configuration surface. Under
[ADR 0008](decisions/0008-every-environment-variable-is-required.md) every variable
is required, has no default, and fails loudly at startup. Never call `os.environ`
from application code.

There are **two exceptions**.

`RENDER_EXTERNAL_HOSTNAME`, in `config/settings/production.py`, which Render
injects and which is absent everywhere else. It cannot go through
`EnvironmentReader`, because those readers require a variable to be present and
this one legitimately is not. It is read with `os.environ.get` in the only settings
module that is already platform-specific — the same file sets
`SECURE_PROXY_SSL_HEADER` for Render's proxy. Anything else reading `os.environ` is
a bug.

`DJANGO_SETTINGS_MODULE`, which Django reads before any settings module loads, so
no settings file can require or validate it. `manage.py` and `config/wsgi.py` fall
back to `local` and `production` respectively; the Makefile passes `local`;
pytest-django passes `test`. `render.yaml` sets it to `production` because the
build runs `manage.py`, whose `local` fallback would collect static files without
a manifest. It is listed in `.env.example` only so the blueprint guard accepts it —
the value in `.env` is never honoured, because `read_env` runs inside `base.py`.

**Migrations.** One per logical change, with a descriptive name
(`0004_add_order_status_index`, not `0004_auto_20260920_1214`). Never edit an applied
migration. A data migration and a schema migration stay in separate files, because
the schema change is what you will want to roll back alone.

**Time.** `django.utils.timezone.now()`, never `datetime.now()`. `USE_TZ = True` and
all stored datetimes are UTC; conversion is the client's concern.

**Money**, if it appears, is `DecimalField`, never float, and the currency is stored
alongside the amount.
