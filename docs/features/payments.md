# Payments

Status: Implemented

Last updated: 2026-09-23

---

## Goal

Take money two ways: cash on delivery, and Khalti. Record what was paid, verify it
against Khalti rather than against the customer's browser, and make fulfilment
impossible to trigger twice.

---

## Scope

What is included in this implementation?

- A `Payment` record per payment attempt
- Cash on delivery, confirmed by the merchant in the admin
- Khalti initiate, redirect return handling, and server-side lookup verification
- Amount verification and idempotency
- The "Verify with Khalti" admin action for stranded payments

What is explicitly outside the scope?

- Refunds. Khalti reports refund statuses but Phase 1 initiates refunds in Khalti's
  own dashboard
- Any second gateway — eSewa, Fonepay, cards
- Partial payments, instalments, or split tender
- Storing card or wallet credentials of any kind
- A webhook endpoint, because Khalti does not send webhooks

---

## Context

[ADR 0005](../decisions/0005-khalti-lookup-is-the-only-verification.md) is the
governing decision and must be read before writing any code here. Its central fact:
**Khalti's ePayment API (KPG-2) sends no webhooks.** The only verification channel
is `POST /epayment/lookup/` with the `pidx` returned at initiation.

That means the redirect back to the storefront is a *trigger*, not evidence. Its
query parameters are attacker-controlled — appending `?status=Completed` to the
return URL must not fulfil anything. Only `pidx` is read from it.

It also means a customer who pays and closes the tab leaves a paid order the system
believes is unpaid, with nothing to detect it. Recovery is the admin action.

[integrations/khalti.md](../integrations/khalti.md) transcribes Khalti's own
published contract: the initiate payload field by field, the callback query
parameters, every lookup status with its HTTP code, and the error bodies. ADR
0005 says what this repository does about Khalti; that document says what
Khalti sends. Read it before writing the client.

[ADR 0004](../decisions/0004-stock-is-committed-at-order-placement.md) means stock
was already decremented before the customer reached Khalti, so payment confirmation
does not touch stock. Cancellation does.

This app must not write order rows directly. Marking an order paid goes through
`apps.orders.services.mark_order_paid`.

---

## Planned

The intended implementation:

- `Payment`: `order` FK, `method`, `status`, `amount`, `pidx` (unique, nullable for
  COD), `transaction_id`, `raw_status`
- `apps/payments/client.py`: a thin Khalti HTTP client owning `initiate` and
  `lookup`, and owning the paisa conversion. It never logs the secret key
- `apps/payments/services.py`: `initiate_khalti_payment`, `verify_khalti_payment`,
  `record_cod_payment`
- `apps/payments/views.py`: `GET /api/v1/payments/khalti/return/`, `AllowAny`,
  reading only `pidx`
- `apps/payments/exceptions.py`: `PaymentNotCompleted`, `PaymentAmountMismatch`,
  `PaymentAlreadyProcessed`
- Settings: `KHALTI_BASE_URL`, `KHALTI_SECRET_KEY`, `KHALTI_RETURN_URL`,
  `STOREFRONT_URL`, all without production defaults
- The admin verify action, per `merchant-admin.md`

---

## Implemented

Both halves. `docs/integrations/khalti.md` transcribes the upstream contract this
was written against; read it before changing anything here.

- `apps/payments/client.py` — `initiate`, `lookup`, and the paisa conversion that
  lives nowhere else
- `apps/payments/selectors.py` — `get_payment_by_pidx`
- `apps/payments/services.py` — `initiate_khalti_payment`, `verify_khalti_payment`
- `apps/payments/views.py`, `urls.py` — `GET /api/v1/payments/khalti/return/`,
  `AllowAny`, its own throttle scope, reading `pidx` and nothing else
- `apps/payments/exceptions.py` — `PaymentNotCompleted`, `PaymentAmountMismatch`,
  `PaymentGatewayUnavailable`
- `apps/orders/` — checkout accepts `khalti` again and returns `payment_url`
- `config/settings/base.py` — `KHALTI_BASE_URL` (sandbox default),
  `KHALTI_SECRET_KEY`, `KHALTI_RETURN_URL`, `STOREFRONT_URL`, `KHALTI_TIMEOUT`,
  and the `payment_return` throttle scope
- `pyproject.toml` — `requests` declared, having been present only transitively
  through `cloudinary`

- `apps/payments/models.py` — `Payment` and `PaymentStatus`, with the **full**
  schema from Data changes including the Khalti columns and the
  `payment_khalti_requires_pidx` constraint. One migration, so the Khalti half
  fills columns that already exist rather than shipping a second one
- `apps/payments/migrations/0001_initial.py`
- `apps/payments/exceptions.py` — `PaymentAlreadyProcessed`
- `apps/payments/services.py` — `record_cod_payment` and `complete_cod_payment`
- `apps/orders/views.py` — `CheckoutView` calls `record_cod_payment` after
  `place_order` commits, at the seam `checkout.md` reserved for the payment handoff
- `apps/payments/tests/` — `PaymentFactory`, `khalti_stubs.py` and 49 tests, plus
  four in `apps/orders/tests/test_checkout.py`

---

## Remaining

- **Refunds.** Lookup reports `Refunded` and `Partially Refunded`, but KPG-2 has no
  refund endpoint: refunds are initiated from Khalti's merchant dashboard. A
  refunded payment currently leaves the order in whatever state it reached, and
  nothing reconciles the two.
- **Nothing detects a customer who pays and closes the tab.** That is a property of
  KPG-2, not a gap here — there is no webhook, and the redirect is the only push
  channel. The Phase 2 answer is the external sweep endpoint ADR 0004, ADR 0005 and
  ADR 0006 all need; build it once, for all three.
- **The live cap.** Khalti applies an initial NPR 200 per-transaction ceiling after
  going live, removable only by completing KYC and contacting support. Most orders
  will exceed it, so this must be cleared before launch, not after the first
  failure.

---

## Decisions

### Decision: COD is recorded at placement and completed by a second service

**Decision**

`record_cod_payment` creates a `pending` payment when the order is placed, from
`CheckoutView`. `complete_cod_payment` is what the merchant's action calls once the
cash is in hand: it marks the payment `completed` and calls
`apps.orders.services.mark_order_paid`.

**Reason**

This document's Scope includes "cash on delivery, confirmed by the merchant in the
admin", but names only `record_cod_payment` under Planned, and
`merchant-admin.md` names only the Khalti verify action. Without a confirm service
there is no way to complete a COD order: the merchant would take the cash and
nothing could mark the order paid except calling `mark_order_paid` directly, which
bypasses the payment record and leaves it `pending` for ever — a payment table that
lies.

Recording at placement rather than at collection is what lets the payment table
answer "what is owed" as well as "what was taken". It also means every order has a
payment row from the moment it exists, which is what `PaymentAdmin` will list.

**Consequence**

A COD payment row exists in `pending` for the life of an unfulfilled order.
`merchant-admin.md` (#10) calls `complete_cod_payment` from `PaymentAdmin`'s
"Mark cash as collected on selected payments" action.

### Decision: the checkout handoff lives in the view, not in `place_order`

**Decision**

`CheckoutView.post` calls `record_cod_payment`, after `place_order` has returned
and its transaction has committed.

**Reason**

Two reasons, and either alone would be sufficient. ADR 0005 requires the payment
handoff to sit outside the placement transaction, and that is the same seam the
Khalti initiate call will use. And this app already imports
`apps.orders.services`; having `apps/orders` import `apps.payments` in return would
close an import cycle between the two apps.

**Consequence**

A COD payment row is written in its own transaction, after the order's. A crash
between the two leaves an order with no payment record — recoverable, and strictly
better than the alternative, where a gateway call inside the placement transaction
holds every variant row lock in the cart across an external HTTP request.

### Decision: the return redirects the browser to the storefront

**Decision**

`GET /api/v1/payments/khalti/return/` verifies, then answers **302**, not JSON. On
success the customer goes to `{STOREFRONT_URL}/orders/{access_token}`; on any
`DomainError` to `{STOREFRONT_URL}/orders/failed?reason=<code>`.

This supersedes the JSON response this document's API section originally described.

**Reason**

Khalti redirects the customer's **browser** here. Every other endpoint in this
system answers an API client, where a JSON 422 is useful; this one answers a person
who has just paid, for whom raw JSON is a dead end with no way forward.

**Consequence**

Three things follow, none of them free:

- **`STOREFRONT_URL` is read by three things** — Khalti's `website_url`, this
  redirect, and the order link in the confirmation email (#9). It was called
  `KHALTI_WEBSITE_URL` when Khalti was its only reader; that was a mistake, and #9
  renamed it. It is the storefront root, not a payment setting.
- **The storefront must serve `/orders/<access_token>` and `/orders/failed`.** That
  is now a contract between the two repositories, and nothing in this one enforces
  it.
- The `access_token` travels in a redirect URL, so it reaches browser history and
  any analytics that log full paths — the exposure ADR 0003 already accepts for the
  emailed link. `SECURE_REFERRER_POLICY = "same-origin"` in `production.py` is what
  keeps it out of referrer headers.

The view therefore catches `DomainError` and redirects, which is a deliberate
exception to `convention.md`'s "no `try`/`except` around service calls". An unknown
`pidx` is **not** caught: `DoesNotExist` reaches the handler as the documented 404,
because a `pidx` this system never issued means a hand-crafted URL, not a customer
coming back from Khalti.

### Decision: a failed initiate returns 422 naming the order

**Decision**

When `initiate` cannot reach Khalti or is refused, `initiate_khalti_payment` raises
`PaymentGatewayUnavailable` with `order_number` in `details`. The checkout response
is a 422.

**Reason**

ADR 0005 puts the initiate call after the placement transaction commits, so by the
time it can fail the order exists and its stock is decremented. A bare error would
leave the customer with no order number and an obvious next move — checking out
again, decrementing the same stock a second time for goods they have already
reserved.

**Consequence**

The storefront can say "order TL-… was placed but we could not reach Khalti". The
order sits in `pending` holding stock until a merchant cancels it, which is the same
standing duty ADR 0004 already creates. There is no retry-payment endpoint; a
customer who wants to pay must place a new order or pay cash on delivery.

### Decision: every Khalti setting is required, in every environment

**Decision**

`KHALTI_BASE_URL`, `KHALTI_SECRET_KEY`, `KHALTI_RETURN_URL`, `STOREFRONT_URL`
and `KHALTI_TIMEOUT` have no defaults. The settings module refuses to import when
any is missing, empty or malformed — the three URLs are validated as URLs, and the
timeout as a number.

**Reason**

[ADR 0008](../decisions/0008-every-environment-variable-is-required.md) applies this
to every variable in the system. This document's original wording, "all without
production defaults", is now true without qualification.

**Consequence**

A developer needs Khalti values in `.env` to run anything, including the catalogue
tests. A placeholder key boots; only a real one takes a payment. `config/settings/test.py`
supplies fakes so the suite needs no merchant account.

`payments.E001` is removed — a check that verifies credentials the settings already
refuse to load without is unreachable, and unreachable validation reads as a
guarantee while doing nothing.

#### Superseded: blank defaults with a system check

> `KHALTI_SECRET_KEY`, `KHALTI_RETURN_URL` and `STOREFRONT_URL` defaulted to
> `""`, and `apps/payments/checks.py` raised `payments.E001` when any was blank and
> `DEBUG` was false — so production refused to start while local and CI ran with no
> credentials at all.

Superseded because it left a misconfigured *sandbox* uncaught: `DEBUG` is true
there, so the failure surfaced as a 422 from the gateway rather than at boot.

### Decision: the return request's parameters are read for `pidx` and nothing else

**Decision**

`status`, `amount`, and `transaction_id` from the redirect are discarded. Only
`pidx` is used, and everything else comes from the lookup response.

**Reason**

The redirect is a GET in the customer's browser. Every parameter is editable.
Reading `status` from it is the most common vulnerability in this class of
integration.

**Consequence**

The customer waits for a server-to-server round trip to Khalti before seeing a
confirmation. That latency is the cost of a real answer, and there is no queue to
defer it to.

### Decision: the looked-up amount is verified against the order total

**Decision**

`verify_khalti_payment` compares the amount Khalti reports against the order's
stored total and raises `PaymentAmountMismatch` on any difference.

**Reason**

Without it, a partial or manipulated payment fulfils a full order. The `pidx` alone
proves a payment happened, not that the right payment happened.

**Consequence**

A mismatch leaves the order unpaid and requires merchant intervention. It should be
logged at `ERROR` — it is either an integration bug or an attack, and both need a
human.

### Decision: fulfilment is idempotent on `pidx`

**Decision**

`Payment.pidx` is unique. Verification checks whether the payment is already
`completed` and returns the same response without re-fulfilling.

**Reason**

The return URL is a plain GET. Customers refresh it, bookmark it, and open it on a
second device.

**Consequence**

The endpoint is safe to call repeatedly, which is also what makes the admin verify
action safe to run on an already-verified payment.

---

## Gotchas

- **`Expired` and `User canceled` arrive as HTTP 400 with a perfectly good body.**
  A client that raises on any non-2xx turns the two most ordinary customer outcomes
  into gateway errors. `client._post` reads the body first and never consults the
  status code; `test_expired_and_user_canceled_are_read_from_a_400_body` pins it.
- **Khalti has two error envelopes.** Authentication failures carry `status_code`,
  validation failures carry `error_key`. There is no single shape to parse, so
  `initiate` judges by the absence of `pidx`/`payment_url` rather than by trying to
  recognise an error.
- **`amount` is inconsistently typed upstream.** Khalti's sample payload sends the
  integer `1300`, every code sample sends the string `"1000"`, and one documented
  error is "A valid integer is required." We send an `int`, which satisfies both
  readings.
- **Amounts cross the Khalti boundary in integer paisa; the database stores
  `DecimalField` rupees.** Conversion lives only in `client.py`. A `Decimal` passed
  to Khalti unconverted charges one hundredth of the intended amount; a paisa
  integer stored in the database inflates every report by a hundred. Khalti's
  minimum is 1000 paisa, so cheap items and test orders can be rejected outright.
- **Khalti's success status is `Completed`, exactly one of seven.** The others —
  `Pending`, `Initiated`, `Refunded`, `Partially Refunded`, `Expired`,
  `User canceled` — all leave the order unpaid. Treating anything except
  `Completed` as success is wrong, including `Pending`.
- The initiate call happens **outside** the checkout transaction. See
  `checkout.md`; this is where holding row locks across an external call would bite.
- `KHALTI_SECRET_KEY` is read in `config/settings/base.py` only and is never
  logged. It falls under `convention.md`'s never-log list, alongside tokens and
  connection strings. Do not log the initiate payload either — it contains customer
  contact details.
- Sandbox and live use different hosts (`test-admin.khalti.com` versus
  `admin.khalti.com`) **and** different keys. A live key against the sandbox host
  fails in a way that looks like a credential problem.
- There is no webhook, so `DEFAULT_PARSER_CLASSES` stays JSON-only. Nothing here
  needs form-encoded parsing or raw-body signature verification.
- **A `KhaltiError` during verification is translated, not propagated.** The caller
  is a customer's browser returning from a payment, and an unhandled `KhaltiError`
  is not a `DomainError`, so it would reach the handler as a 500 JSON page for
  someone who has just paid. `verify_khalti_payment` re-raises it as
  `PaymentGatewayUnavailable`, which the return view turns into the failure
  redirect. `initiate_khalti_payment` does the same for the same reason.
- **`client.lookup` validates both fields its callers index**, `status` and
  `total_amount`. An unknown `pidx` comes back as
  `{"detail": "Not found.", "error_key": "validation_error"}`, which has neither,
  and Khalti's two error envelopes are too different to recognise by shape — so the
  client guarantees what it promises rather than letting a `KeyError` become a 500.
- **What Khalti reported is saved before any branch, outside the transaction.**
  Written inside a block that then raises, `raw_status` and `transaction_id` would
  roll back with it and leave no trace of the refusal — exactly the record support
  needs when a customer says they paid.
- **`verify_khalti_payment` checks our own table before calling Khalti.** An
  unknown `pidx` raises `DoesNotExist` without spending an outbound call on an
  identifier this system never issued, which also keeps the endpoint from being a
  way to make the server talk to Khalti on demand.
- **The verification lock is load-bearing.** Verified meaningful: with
  `select_for_update()` removed, two concurrent returns for one `pidx` leave the
  loser raising `InvalidStatusTransition` from the orders layer — a customer who
  refreshes the return URL would see a failure redirect instead of their order.
- **The amount comparison happens outside the lock**, deliberately: an order's
  total cannot change after placement, so only fulfilment needs serialising.
- COD orders have no `pidx`. The uniqueness constraint must permit multiple nulls,
  which Postgres does by default — do not "fix" this with a default value.
- **`transaction_id` and `raw_status` are `blank=True, default=""`, not nullable**,
  although Data changes called them nullable. For those two, `""` and `NULL` would
  mean the same thing, and a string column with two spellings of absent is what
  ruff's `DJ001` exists to prevent. `pidx` keeps its `NULL` because the unique
  constraint depends on NULLs being distinct — that is a real difference, and the
  linter exempts a unique column for exactly that reason.
- **`complete_cod_payment` locks the payment row.** Its status check guards a state
  change on the *order*, which makes it a read-then-write on shared state. Verified
  meaningful: with `select_for_update()` removed, two merchants confirming the same
  cash both pass the check, and the loser surfaces `InvalidStatusTransition` from
  the orders layer instead of `PaymentAlreadyProcessed` — the right rollback by
  accident rather than the intended guard.
- `mark_order_paid` is called **inside** `complete_cod_payment`'s transaction, so a
  rejected order transition rolls the payment back. A completed payment against an
  order that never moved would be worse than a failed confirmation.

---

## API

### Endpoint

```text
GET /api/v1/payments/khalti/return/?pidx=...
```

Initiation is not a public endpoint. It happens inside `POST /api/v1/checkout/`,
which returns the `payment_url`.

### Response

**A 302, not a body** — see the decision above. Khalti sends the customer's browser
here, so the endpoint hands it on to the storefront:

```text
302 Location: {STOREFRONT_URL}/orders/{access_token}          paid
302 Location: {STOREFRONT_URL}/orders/failed?reason=<code>    anything else
```

`reason` is the `DomainError`'s published code, so the storefront branches on the
same vocabulary as every API client: `payment_not_completed`,
`payment_amount_mismatch`.

Checkout's own response carries `payment_url` for Khalti and omits the key
entirely for cash on delivery.

### Errors

404 for an unknown `pidx`, as a JSON envelope rather than a redirect — the same 404
as any other missing resource, so the endpoint does not confirm which `pidx` values
exist, and a hand-crafted URL is not handed a storefront page.

`POST /api/v1/checkout/` answers 422 `payment_gateway_unavailable` when initiation
fails, with the order number in `details`:

```json
{
  "error": {
    "code": "payment_gateway_unavailable",
    "message": "The order was placed but payment could not be started.",
    "details": { "order_number": "TL-2026-000142" }
  }
}
```

---

## Data changes

**`payment`** — UUID pk, timestamps, `order` FK (`PROTECT`), `method` (`cod` or
`khalti`), `status` (`pending`, `completed`, `failed`), `amount` (`DecimalField`),
`pidx` (unique, nullable), `transaction_id` (blank), `raw_status` (blank).

The last two are blank rather than nullable as first written; see Gotchas.
Indexes on `pidx` and `(status, -created_at)`.
Constraints: `amount >= 0`; `pidx` present when `method` is `khalti`.

`order` is `PROTECT` — a payment record must outlive any attempt to tidy up orders.

One migration. No data migration.

---

## Permissions

`AllowAny` on the return endpoint, declared explicitly. It has to be: the customer
arrives from Khalti's domain with no session and, under ADR 0003, no account.

What protects it is not authentication but the shape of what it accepts. It takes a
single opaque `pidx`, believes nothing else in the request, and resolves the true
state by calling Khalti server-to-server with a secret the caller does not have.
Possession of a `pidx` grants only the ability to trigger a verification that
Khalti itself adjudicates.

The endpoint is idempotent and throttled under the `payment_return` scope. It is
the only unauthenticated endpoint in the system that can change money state.

Staff trigger verification through the admin, requiring `is_staff`.

---

## Tests

49 tests. Khalti is stubbed at the HTTP boundary throughout — `conftest.py`'s
`khalti_post` patches `apps.payments.client.requests.post`, and
`apps/payments/tests/khalti_stubs.py` holds the response bodies. **No test reaches
the network**, and `config/settings/test.py` points `KHALTI_BASE_URL` at an
`.invalid` host so nothing can.

`apps/payments/tests/test_client.py`:

- `test_amount_is_converted_to_paisa_on_initiate` and
  `test_lookup_response_amount_is_converted_to_rupees`
- `test_the_authorization_header_carries_the_key_prefix`
- `test_every_call_carries_a_timeout`
- `test_expired_and_user_canceled_are_read_from_a_400_body` — parametrised
- `test_a_transport_failure_raises_khalti_error`,
  `test_a_non_json_response_raises_khalti_error`,
  `test_an_initiate_without_a_payment_link_raises_khalti_error`
- `test_secret_key_and_customer_details_are_never_logged`

`apps/payments/tests/test_khalti.py`:

- `test_initiate_records_a_pending_payment_and_returns_the_payment_url`
- `test_initiate_sends_the_order_number_as_the_purchase_order_id`
- `test_initiate_failure_raises_naming_the_order`
- `test_completed_lookup_marks_the_order_paid`
- `test_only_completed_fulfils` — parametrised over all six non-success statuses
- `test_amount_mismatch_does_not_fulfil_and_is_logged_at_error`
- `test_a_second_verification_does_not_refulfil`
- `test_an_unknown_pidx_raises_rather_than_calling_khalti`
- **`test_lookup_is_not_called_inside_transaction`** — the twin of
  `checkout.md`'s `test_gateway_is_not_called_inside_transaction`, for the
  verification side. `verify_khalti_payment` takes a row lock to fulfil, and the
  lookup must not be held under it. Compares transaction nesting depth, because
  `django_db` makes `in_atomic_block` true throughout every test
- `test_a_lookup_failure_is_translated_for_the_browser` and
  `test_a_lookup_missing_total_amount_does_not_fulfil`

`apps/payments/tests/test_api.py`:

- `test_return_with_completed_lookup_marks_order_paid`
- `test_return_redirects_to_the_storefront_with_the_access_token`
- **`test_return_ignores_status_parameter_from_query_string`** — sends
  `status=Completed` alongside a `User canceled` lookup. Future context calls this
  the most important test in the repository; it is
- `test_return_with_user_canceled_lookup_leaves_order_pending`
- `test_return_for_a_failed_payment_redirects_with_a_reason`
- `test_return_with_amount_mismatch_returns_422_and_does_not_fulfil`
- `test_second_return_for_same_pidx_does_not_double_fulfil`
- `test_return_with_unknown_pidx_returns_404`, `test_return_without_a_pidx_returns_404`
- `test_a_gateway_outage_redirects_rather_than_erroring` — a customer who has paid
  must never meet a 500 here
- `test_concurrent_returns_fulfil_once`

`apps/payments/tests/test_services.py` and `test_models.py` carry the COD half.
`apps/orders/tests/test_checkout.py` adds `test_khalti_checkout_returns_a_payment_url`,
`test_cod_checkout_omits_the_payment_url` and
`test_a_failed_initiate_returns_422_naming_the_order`.

---

## Files

```text
apps/payments/
├── models.py
├── client.py
├── selectors.py
├── services.py
├── views.py
├── urls.py
├── exceptions.py
├── migrations/
│   └── 0001_initial.py
├── tests/
│   ├── factories.py
│   ├── khalti_stubs.py
│   ├── test_models.py
│   ├── test_services.py
│   ├── test_client.py
│   ├── test_khalti.py
│   ├── test_api.py
│   └── test_admin.py
└── admin.py                     verify with Khalti, mark cash collected
apps/orders/views.py             the checkout branch
apps/orders/serializers.py       payment_method widened back
config/settings/base.py          KHALTI_*, the payment_return rate
config/settings/test.py          .invalid hosts and fake keys
.env.example                     KHALTI_*, STOREFRONT_URL, the return rate
config/urls.py                   the return route
conftest.py                      the khalti_post fixture
pyproject.toml                   requests declared
```

---

## Future context

`test_return_ignores_status_parameter_from_query_string` is the most important test
in this repository. It is the difference between a store and a free shop. Do not
delete it as redundant.

The absence of a webhook is a property of Khalti, not an oversight. If Khalti adds
one later, the webhook becomes a trigger for reconciliation — lookup stays
authoritative, because a webhook payload is also just a claim.

The stranded-payment problem — paid, tab closed, nothing detected — is the most
likely source of real customer complaints in Phase 1. The admin action is the
Phase 1 answer. The Phase 2 answer is an external cron calling an authenticated
sweep endpoint that re-runs lookup for every pending payment, which is the same
mechanism ADR 0004 and ADR 0006 both need. Build it once, for all three.
