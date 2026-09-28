# API error contract

Status: Implemented

Last updated: 2026-09-26

---

## Goal

Make the exception handler emit the error codes that `architecture.md` publishes
as the API contract, stated in one place rather than inherited from DRF's internal
`default_code`.

---

## Scope

What is included in this implementation?

- A `DomainError` base class in `apps/core/exceptions.py`, with `code`, `message`,
  `details`, and `status_code = 422`
- A `DomainError` branch in `api_exception_handler`
- An explicit exception-class to published-code map, replacing the reliance on
  `exc.default_code`
- Tests covering every row of the status/code table

What is explicitly outside the scope?

- The envelope shape, which already exists and is correct
- Per-domain exception subclasses — each feature defines its own
- Changing any status code that is already correct
- Logging behaviour, which is already implemented and correct

---

## Context

`apps/core/exceptions.py` already produces the right envelope:

```json
{ "error": { "code": "...", "message": "...", "details": {} } }
```

`_envelope()` and `_describe()` build it, and the handler already converts Django's
`ValidationError` to DRF's, maps `IntegrityError` to 409, and turns unhandled
exceptions into a logged 500. All of that is correct and stays.

`DomainError` exists in `apps/core/exceptions.py`, with the class body
`convention.md` prescribes, and the handler branches on it first and returns
`exc.status_code` with the subclass's `code`. The unhandled-exception path already
emits `server_error`. No domain subclasses exist yet; each feature defines its own.

The handler now resolves every code through `_PUBLISHED_CODES`, a literal map from
exception class to published code. `exc.default_code` is no longer read.

`convention.md` states that `code` is part of the public API and that renaming one
is a breaking change. Fixing this before any client exists costs nothing; fixing it
after the Next.js storefront branches on codes is a coordinated release.

---

## Planned

The intended implementation:

- A module-level map from DRF exception class to published code, replacing the
  `exc.default_code` read, so the contract is stated in one greppable place rather
  than inferred from DRF's internals
- `apps/core/exceptions.py` logging through `apps.core.logging.get_logger`, so its
  two log lines carry the request id like every other module
- `apps/core/tests/test_exceptions.py` covering each mapped condition

---

## Implemented

- `apps/core/exceptions.py` — `DomainError` base class with `code`, `message`,
  `status_code = 422`, and a keyword-only `__init__` taking `message` and `details`
- `apps/core/exceptions.py` — `api_exception_handler` branches on `DomainError`
  first, returning `exc.status_code` with the subclass's `code`
- `apps/core/exceptions.py` — `IntegrityError` returns 409 `conflict`
- `apps/core/exceptions.py` — unhandled exceptions return 500 `server_error` with
  no exception text in the body
- `apps/core/exceptions.py` — `_PUBLISHED_CODES` maps every exception the API
  raises to its published code; an unpublished `APIException` reports the generic
  `error` rather than leaking DRF's internal name
- `apps/core/exceptions.py` — logs through `apps.core.logging.get_logger`
- `apps/core/exceptions.py` — `ObjectDoesNotExist` returns 404 `not_found`, added
  by `catalog-browsing` (#5). `convention.md` had told selectors to let
  `DoesNotExist` propagate and let the handler answer 404 since before this
  feature, but no such branch existed and none was noticed, because no selector
  had an HTTP caller until #5. An unknown slug would have been a logged 500
- `apps/core/exceptions.py` — Django's `SuspiciousOperation` family returns 400
  `parse_error` and logs `request.suspicious_operation` at warning. Django raises
  these while parsing a malformed or oversized body (`TooManyFieldsSent`,
  `RequestDataTooBig`). Before this they fell through to the 500 path: an image
  sent with a url-encoded `Content-Type` split its bytes on `&` into more than
  `DATA_UPLOAD_MAX_NUMBER_FIELDS` fields and was reported as a server error
- Every published code is now reachable from a real endpoint. The 422 row closed
  with `checkout` (#7); the 404 row is produced by the `ObjectDoesNotExist` branch
  on every selector miss; 409 is produced by the catalogue's uniqueness
  constraints
- `apps/core/tests/test_exceptions.py` — 32 tests covering the `DomainError`
  mapping, per-raise message override, Django and DRF validation errors, every row
  of the status/code table, the 409 conflict path, the 400 path for Django's
  suspicious-request errors, the 500 path and its logging,
  the generic fallback, and a parametrised check that every failure shares one
  envelope shape

---

## Remaining

None for the published-code contract itself.

Nothing. The feature is closed.

The condition it was waiting on is met: `VariantUnavailable` and
`InsufficientStock`, defined by `product-catalog` in `apps/catalog/exceptions.py`
and raised by `apps.catalog.services`, now reach a client as 422s through
`POST /api/v1/checkout/`, and `apps/orders/tests/test_checkout.py` asserts both
codes over HTTP. The 422 row is no longer exercised only from unit tests.

The 429 row is DRF's own throttles over the database cache (ADR 0014). Later
features added codes through `DomainError` subclasses only: `product_has_no_variants`
(admin API), `invalid_refresh_token` (logout), and the order transition codes, now
reachable over `/api/v1/admin/orders/{id}/transition/`. A staff login failure is
`401 authentication_failed`, whatever the reason.

---

## Decisions

### Decision: the published code map is explicit, not derived

**Decision**

The handler holds a literal map from exception class to published code, rather than
reading `exc.default_code`.

**Reason**

`default_code` belongs to DRF. A DRF upgrade that renames one silently changes this
API's public contract, and nothing would fail until a client broke in production.

**Consequence**

Adding a new DRF exception to the API surface requires adding a row to the map. An
unmapped exception falls back to a generic code rather than leaking an internal
one.

### Decision: `DomainError` defaults to 422, not 400

**Decision**

`status_code = 422`.

**Reason**

400 means the request was malformed; the serializer already owns that. 422 means
the request was well-formed and the business rejected it — out of stock, order
already shipped. Clients need to tell these apart, because one is a bug in their
code and the other is a state they must show the user.

**Consequence**

A subclass may override `status_code` where a different code is genuinely right,
but the default is deliberate and should rarely be overridden.

---

## Gotchas

- The handler runs for **every** endpoint, including the two health endpoints,
  which opt out of authentication and throttling but not out of exception handling.
- `X-Request-ID` is listed in `CORS_EXPOSE_HEADERS`; without it a browser hides the
  header from the storefront's scripts, which quote it in error messages.
- `_describe()` already flattens a DRF `ValidationError` detail dict into
  `details`, so field errors land keyed by field name. Do not reimplement this.
- The `IntegrityError` branch returning 409 is deliberate and predates this work.
  It is how `convention.md`'s "let the database enforce uniqueness and translate
  the failure" rule surfaces to clients.
- Domain exceptions are **raised, never returned**. A service returning
  `(None, "error")` is a review rejection, per `convention.md`.
- `DomainError` is not a DRF `APIException`. The handler branch must come before
  DRF's own handling, or it falls through to the 500 path. It already is first —
  keep it there.
- **A passing test suite does not mean this feature is done.** The code the tests
  assert against is the code that disagrees with `architecture.md`. Read the status
  table, not the green run.
- **`SuspiciousOperation` is a client error, not a server one.** Django's own
  handler answers it with 400; DRF's does not know it, so without the branch it
  was a logged 500. The response is DRF's flat parse error, never Django's
  message, which names the setting that was exceeded.
- **`ObjectDoesNotExist` is mapped before DRF's handler runs**, so a `.get()` that
  misses anywhere below the view becomes a 404 rather than a 500. That is the
  contract `convention.md` promises selectors, and the cost is that a genuine
  lookup bug in a service also presents as 404. The message is DRF's flat "Not
  found.", never Django's, which names the model.

---

## API

No new endpoints. This changes the error body of every existing and future
endpoint.

### Response

```json
{
  "error": {
    "code": "insufficient_stock",
    "message": "Not enough stock to fulfil this order.",
    "details": { "variant_id": "...", "requested": 3 }
  }
}
```

### Errors

The full status and code table lives in
[architecture.md](../architecture.md#error-handling). It is not duplicated here;
`convention.md` warns that a second copy will drift.

---

## Data changes

None.

---

## Permissions

None. The handler runs after authentication and permission checks have already
produced their exceptions.

Note one existing rule this work must preserve: a hidden object returns 404, not
403, so the API does not confirm that an identifier exists to a caller not entitled
to know.

---

## Tests

All in `apps/core/tests/test_exceptions.py`:

- `test_published_codes_do_not_depend_on_drf_internals` — parametrised over every
  row of the status/code table, and the reason the map exists
- `test_an_unpublished_api_exception_keeps_its_status_and_reports_a_generic_code` — an unmapped
  exception reports `error`, not DRF's internal name
- `test_domain_error_maps_to_422_and_its_own_code`
- `test_validation_error_uses_the_documented_code_not_drf_default`
- `test_validation_error_message_is_the_first_field_error`
- `test_django_validation_error_is_translated_into_the_envelope`
- `test_integrity_error_maps_to_409_conflict` and
  `test_integrity_error_response_carries_no_database_detail`
- `test_unhandled_exception_maps_to_500_server_error_without_detail` and
  `test_unhandled_exception_is_logged_with_its_traceback`
- `test_a_missing_object_maps_to_404_so_selectors_need_not_catch_it` and
  `test_a_missing_object_response_carries_no_lookup_detail` — the
  `ObjectDoesNotExist` branch, and that Django's model-naming message is
  discarded
- `test_a_suspicious_request_body_maps_to_400_parse_error_without_detail` —
  `TooManyFieldsSent` is a 400 `parse_error`, logged as a warning and not as an
  unhandled exception
- `test_every_failure_shares_one_envelope_shape`

---

## Files

```text
apps/core/
├── exceptions.py
└── tests/
    └── test_exceptions.py
```

---

## Future context

Every feature document after this one defines domain exceptions in
`apps/<domain>/exceptions.py` subclassing `DomainError`. If this work is
incomplete, those subclasses have no base and every service that raises will
produce a 500 instead of a 422.

The 500 response must never carry exception text; the detail goes to the log with
the request id from `RequestIDMiddleware`. That is already implemented — do not
"improve" it by adding the exception message to the response.
