# ADR 0006: Transactional email sends in-request, on commit

Status: Accepted

Date: 2026-09-20

Supersedes: None

---

## Context

Two emails matter in Phase 1: the order confirmation, and the shipping
notification. Both are triggered by a database write — one by checkout, one by a
merchant action in the admin.

`architecture.md` forbids a task queue outright and states that every unit of work
completes inside the request that started it. It says nothing about email, which
leaves the hard part undecided: an SMTP call is a slow, failure-prone network
operation, and the obvious place to put it is inside the service that just wrote
the order.

That obvious place is wrong in a specific way. A service function is wrapped in
`transaction.atomic()`. An SMTP timeout inside that block raises, the transaction
rolls back, and an order the customer has already paid for disappears.

## Decision

**Email is sent from `transaction.on_commit`.** The service registers the callback
inside its transaction; Django runs it after the commit succeeds.

**Failures are caught, logged at `ERROR`, and never propagated.** A failed email
does not fail the request that triggered it.

**There is no retry, and no outbox table.** One attempt per event.

**`apps/core/email.py` owns the mechanism**, exposing a domain-agnostic
`send_email(*, to, subject, template_name, context)` that knows nothing about
orders — `core` must not import from a domain app. **`apps/orders/emails.py` owns
the content**: the templates, the subject lines, and the `on_commit` trigger
points.

## Reason

`on_commit` is what separates the two failure modes that must not be confused. The
order is durable before the email is attempted, so an email failure can never
destroy a sale. That is the property worth having, and it costs nothing.

Swallowing the failure follows from there. Once the order is committed, there is
nothing useful to tell the customer — the request that would show them an error is
about to render their confirmation page, and the order genuinely succeeded. Raising
would turn a successful purchase into a 500.

Not retrying follows from the architecture. A retry needs somewhere to retry *from*,
and with no queue and no scheduler that means an outbox table plus an externally
triggered drain endpoint — a table, a service, an endpoint, a deployment
dependency, and a new monitoring obligation. That is a feature, and Phase 1 does
not need it enough to pay for it.

## Alternatives considered

### Send inside the service, inside the transaction

Why it was not chosen: an SMTP timeout rolls back a paid order. This is the failure
mode the decision exists to prevent.

### Send in the view, after the service returns

Why it was not chosen: it puts a business consequence in the HTTP layer, which
`architecture.md` forbids, and it means every endpoint that creates an order has to
remember to send the email. The admin action would not, so a merchant marking an
order shipped would send nothing — exactly the bug ADR 0002 exists to prevent.

### An outbox table drained by an external cron

Why it was not chosen for Phase 1: it is the correct design and it should be the
first thing added when email reliability matters. It is rejected now on cost, not
on correctness. If it is ever built, `apps/notifications` becomes a real app,
because it would finally own a table.

### A third-party service with its own retry (Resend, Postmark)

Why it was not chosen as a *substitute* for this decision: a provider retries
delivery to the recipient's mail server, not the API call that failed to reach the
provider. If the outbound HTTP call fails, provider-side retry never happens. A
provider is still recommended as the transport; it just does not change where the
send is triggered or what happens when it fails.

## Consequences

### Positive

- A paid order is never lost to an email failure.
- One trigger point per event, reachable from both the API and the admin.
- `core` stays free of domain knowledge, so a future feature that sends a different
  email reuses the mechanism without touching orders.

### Negative

- **A customer can have an order with no confirmation email and no automatic
  retry.** With ADR 0003's guest checkout, that email also carries their order
  access token — so a failed send means a customer who cannot reach their own
  order. These two decisions compound, and the merchant's only recovery is the
  admin.
- The failure is invisible to the customer and visible only in logs. Nothing alerts
  anyone.
- Checkout latency includes an SMTP round trip. On Render's smaller instances this
  occupies a worker for its duration, in the same way image upload does.

### Constraints introduced

- Every transactional email is registered with `transaction.on_commit`, never
  called directly inside `atomic()`.
- `send_email` catches broadly and logs at `ERROR` with enough context to identify
  the order — and, per `convention.md`'s never-log list, logs the order id rather
  than the recipient's full email address.
- `apps/core/email.py` may not import from any domain app.
- `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, and the SMTP credentials are read in
  `config/settings/base.py` only. `base.py` currently configures no email at all —
  only `local.py` sets a console backend — so production cannot send mail until
  this is added.
- A resend action exists in the admin for both emails. Without it, the negative
  consequence above has no remedy at all.

## Implementation

```text
apps/core/email.py         send_email; catches, logs, never raises
apps/orders/emails.py      templates, subjects, on_commit trigger points
apps/orders/services.py    registers callbacks inside their transactions
apps/orders/admin.py       resend confirmation / resend shipping actions
config/settings/base.py    EMAIL_BACKEND, DEFAULT_FROM_EMAIL, SMTP settings
docs/features/transactional-email.md
```

## Future reconsideration

Revisit as soon as a missed confirmation email causes a real support incident —
which, given that the email carries the order access token, is more likely here
than in a store with customer accounts.

The upgrade path is an outbox table plus an externally triggered drain endpoint,
built together with the reconciliation sweep that ADR 0004 and ADR 0005 both
anticipate needing. Three decisions converge on the same missing mechanism; build
it once.
