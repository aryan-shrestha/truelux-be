# ADR 0011: Cash on delivery only

Status: Accepted

Date: 2026-09-25

Supersedes: [ADR 0005](0005-khalti-lookup-is-the-only-verification.md)

---

## Context

The clothing codebase this project was forked from took Khalti payments. The
TrueLux demo must run without payment-gateway credentials, and the client has asked
for a basic store first. Under cash on delivery nothing is "paid" at the time the
merchant acts on an order, so the `paid` status describes an event that does not
happen.

---

## Decision

Checkout accepts only `payment_method = "cod"`. The Khalti client, the return
endpoint, the `KHALTI_*` settings and the payment-record states that only Khalti
used are removed. `OrderStatus.PAID` is renamed to `CONFIRMED`: the merchant confirms
a COD order (typically by phone) before shipping it.
The flow is `pending → confirmed → shipped → delivered`. `cancelled` is reachable
from `pending` and `confirmed`.

---

## Reason

There is less to configure, less to deploy and less to fail during a demo. The
removed code stays in the clothing-store repository if online payment is needed
later.

---

## Alternatives considered

### Keep Khalti behind a feature flag

Why it was not chosen: [ADR 0008](0008-every-environment-variable-is-required.md)
would still require its variables, and dead code would stay untested in practice.

---

## Consequences

### Positive

- No gateway account is needed to run or deploy.

### Negative

- Adding online payment later is a feature, not a toggle.

### Constraints introduced

- `PaymentMethod` has one member. Clients must not offer another.

---

## Implementation

```text
apps/payments/
apps/orders/constants.py
apps/orders/services.py
docs/features/payments.md
```
