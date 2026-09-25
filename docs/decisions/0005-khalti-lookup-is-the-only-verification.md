# ADR 0005: Khalti lookup is the only payment verification

Status: Superseded by [ADR 0011](0011-cash-on-delivery-only.md)

Date: 2026-09-20

Supersedes: None

---

## Context

Most payment gateways tell a merchant about a payment twice: the customer's browser
returns to a `return_url`, and the gateway POSTs a webhook server-to-server. The
standard design treats the webhook as authoritative, because a browser can be
closed, spoofed, or replayed.

**Khalti's ePayment API (KPG-2) does not send webhooks.** Its documented flow is:

1. `POST /epayment/initiate/` with `amount` (in paisa), `purchase_order_id`,
   `return_url`, and `website_url`, authenticated with `Authorization: Key <secret>`
2. Khalti returns a `pidx` and a `payment_url`
3. The customer pays and is redirected to `return_url` with query parameters
   including `pidx`, `status`, `transaction_id`, and `amount`
4. The merchant calls `POST /epayment/lookup/` with the `pidx`

The full published contract — payloads, callback parameters, every lookup
status, and the error bodies — is transcribed in
[integrations/khalti.md](../integrations/khalti.md).

Khalti's own documentation instructs merchants to confirm via lookup after the
redirect. There is no second channel. If the browser never comes back, nothing
tells the backend anything.

## Decision

**The redirect's query parameters are an untrusted trigger, never evidence.** They
are used for exactly one thing: extracting `pidx`. Nothing else in the redirect —
`status`, `amount`, `transaction_id` — is read or believed.

**`POST /epayment/lookup/` is the sole source of truth.** It is called
server-to-server, inline, during the handling of the return request.

**Only `Completed` fulfils.** Khalti returns one of `Completed`, `Pending`,
`Initiated`, `Refunded`, `Partially Refunded`, `Expired`, or `User canceled`. Every
status other than `Completed` leaves the order unpaid.

**The looked-up amount is verified against the order total** before fulfilment. A
mismatch is a `DomainError`, not a fulfilment.

**Fulfilment is idempotent on `pidx`.** `Payment.pidx` is unique. A second return
for the same `pidx` finds the payment already `Completed` and returns the same
response without re-fulfilling.

**Amounts cross the boundary in paisa.** The database stores `DecimalField` rupees;
conversion to and from integer paisa happens only in the Khalti client, nowhere
else.

**Unreturned payments are reconciled manually.** A "Verify with Khalti" admin
action re-runs lookup for any `pending` payment with a `pidx`.

## Reason

There is no choice about lookup being authoritative — it is the only channel that
exists. What this ADR actually decides is the consequences of that, and those are
not obvious.

Calling lookup inline, during the return request, means the customer waits for an
HTTP round trip to Khalti before seeing their confirmation page. That is the right
trade: the alternative is showing them a "we're checking" page with nothing to
resolve it, since there is no queue to resolve it from.

Verifying the amount matters because `purchase_order_id` is merchant-supplied and
the initiate payload is constructed client-adjacent. Trusting the redirect's
`amount` parameter would let a customer alter what they appear to have paid; even
with lookup, an unverified amount means a partial payment could fulfil a full order.

Idempotency on `pidx` matters because the return URL is a plain GET in a browser.
The customer will refresh it. Some will bookmark it.

## Alternatives considered

### Trust the redirect's `status=Completed` parameter

Why it was not chosen: it is a query string under the customer's control. Appending
`?status=Completed&pidx=<anything>` to the return URL would fulfil an order. This is
not a subtle risk; it is the most common integration vulnerability in this class of
gateway.

### Poll Khalti for pending payments on a schedule

Why it was not chosen: nothing can run a schedule. It would require an external
cron calling an authenticated endpoint — a new deployment dependency and a new
public surface for a problem that the admin action solves manually at Phase 1
volume.

### Ask Khalti to enable webhooks

Why it was not chosen: KPG-2 does not offer them. This is a property of the
gateway, not a configuration.

### Use eSewa instead, if it offers a callback

Why it was not chosen: the gateway choice is the merchant's, driven by what their
customers already have installed. The verification pattern would be similar
regardless.

## Consequences

### Positive

- No webhook means no unauthenticated, CSRF-exempt, internet-reachable POST
  endpoint. The highest-risk surface in a typical payment integration does not
  exist here.
- `DEFAULT_PARSER_CLASSES` stays JSON-only. No form-encoded parsing, no raw-body
  signature verification, no parser conflict.
- One verification path means one place to get right.

### Negative

- **A customer who pays and closes the tab before the redirect completes leaves a
  paid order that the system believes is unpaid.** Their money is taken and their
  order does not progress. Nothing detects this automatically.
- Recovery depends entirely on the merchant noticing and running the admin action.
  If they never look, the customer's only route is to complain.
- The confirmation page is as slow as Khalti's lookup endpoint. A Khalti outage
  during the return means the customer sees an error after paying successfully.
- Refunds are out of band. Khalti reports `Refunded` and `Partially Refunded`
  statuses, but Phase 1 initiates refunds through Khalti's own dashboard, not
  through this API.

### Constraints introduced

- `Payment.pidx` is unique. Fulfilment checks it before acting.
- The Khalti secret key is read in `config/settings/base.py` only, never elsewhere,
  and is never logged — it falls under `convention.md`'s never-log list.
- The initiate call happens **outside** the order-placement transaction. It is an
  external call of unbounded duration and would otherwise hold both a Supabase
  pooler slot and the variant row locks from ADR 0004.
- Paisa/rupee conversion lives exclusively in the Khalti client module. A
  `DecimalField` value must never be passed to Khalti unconverted, and a paisa
  integer must never be stored.
- The sandbox host (`test-admin.khalti.com`) and the live host
  (`admin.khalti.com`) differ, as do their keys. Both come from environment
  variables with no production default.

## Implementation

```text
apps/payments/models.py      Payment (pidx unique, status, amount)
apps/payments/services.py    initiate_khalti_payment, verify_khalti_payment
apps/payments/client.py      HTTP client; paisa conversion; never logs the key
apps/payments/views.py       return handler (AllowAny, reads pidx only)
apps/payments/admin.py       "Verify with Khalti" action
config/settings/base.py      KHALTI_BASE_URL, KHALTI_SECRET_KEY
docs/features/payments.md
```

## Future reconsideration

Revisit if Khalti introduces webhooks, at which point the webhook becomes a
reconciliation trigger — but lookup stays authoritative, because a webhook payload
is still just a claim.

Revisit if abandoned-but-paid orders become frequent enough that manual
reconciliation is unreliable. The answer is an external cron calling an
authenticated sweep endpoint that re-runs lookup for pending payments, which is the
same mechanism ADR 0004 would need for stock release — build them together.
