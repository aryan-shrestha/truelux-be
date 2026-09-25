# Payments

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Record what each order owes. TrueLux takes cash on delivery only
([ADR 0011](../decisions/0011-cash-on-delivery-only.md)), so a payment is a record of
the cash the courier will collect, and of when it was collected.

---

## Scope

What is included in this implementation?

- A `Payment` row per order, created at checkout, `pending`
- A service and a Django admin action that mark the cash collected
- Cash on delivery as the only `PaymentMethod`

What is explicitly outside the scope?

- Any online payment gateway. Khalti, which the fork supported, was removed.
- Refunds, partial payments, payment through the admin API
- Tying the order's status to the payment

---

## Context

`checkout.md` places the order; `CheckoutView` then calls `record_cod_payment`. The
order lifecycle (`pending → confirmed → shipped → delivered`, `cancelled`) belongs to
`orders.md` and moves independently of the payment: under COD the merchant confirms
by phone and the cash arrives at delivery.

---

## Implemented

- `apps/payments/models.py` — `Payment`: `order` (`PROTECT`), `method`
  (`PaymentMethod.choices`, only `cod`), `status` (`pending`, `completed`),
  `amount`. Check constraint `payment_amount_not_negative`; index on
  `(status, -created_at)`.
- `apps/payments/services.py` — `record_cod_payment(order)` creates the pending row
  for `order.total`; `complete_cod_payment(payment)` locks the row, raises
  `PaymentAlreadyProcessed` unless it is pending, and marks it `completed`. It does
  not touch the order.
- `apps/payments/admin.py` — `PaymentAdmin`, fully read-only, no add permission, with
  the **Mark cash as collected on selected payments** action, which reports
  successes and failures per row.
- `apps/orders/constants.py` — `PaymentMethod` has one member, `COD`.
- `apps/orders/management/commands/seed_orders.py` — seeded delivered orders have
  their payment completed; every other seeded payment is pending.

---

## Remaining

None.

---

## Decisions

### Decision: cash collection does not move the order

**Decision**

`complete_cod_payment` only records the cash. The fork's version also marked the
order paid.

**Reason**

ADR 0011 renames `paid` to `confirmed`, which the merchant sets after a phone call,
long before any cash exists. Coupling the two would either confirm an order at
delivery or record cash that was never handed over.

**Consequence**

A delivered order can still show a pending payment until someone records the cash.

### Decision: the payment is recorded after the order commits

**Decision**

`CheckoutView` calls `record_cod_payment` after `place_order` returns.

**Reason**

It keeps `place_order` free of a dependency on `payments`, which already depends on
`orders`.

**Consequence**

If that insert fails, the order exists without a payment row and the customer sees a
500 (`test_a_failed_cod_record_leaves_an_order_with_no_payment` pins this down).

---

## Gotchas

- `PaymentStatus` has no `failed` state any more; it existed only for Khalti.
- The admin API has no payment endpoints. Cash collection is a Django admin action.
- `Payment.order` is `PROTECT`, so `seed_orders --flush` deletes payments first.

---

## Data changes

`payment` table: `id`, `order_id`, `method`, `status`, `amount`, timestamps. The
Khalti columns (`pidx`, `transaction_id`, `raw_status`) and the
`payment_khalti_requires_pidx` constraint are gone. Migrations were regenerated as a
fresh `0001_initial`.

---

## Permissions

No API surface. `PaymentAdmin` is for Django admin users.

---

## Tests

- `apps/payments/tests/test_services.py` — recording leaves the order pending;
  completion leaves the order status alone; completing twice raises
  `PaymentAlreadyProcessed`; two concurrent completions complete once.
- `apps/payments/tests/test_admin.py` — the collect action, its per-row failure
  message, no manual add, read-only fields.
- `apps/payments/tests/test_models.py` — negative amounts violate the constraint;
  an order with a payment cannot be deleted.
- `apps/orders/tests/test_checkout.py` — COD checkout records a pending payment;
  `payment_method: "khalti"` is a 400.

---

## Files

```text
apps/payments/
├── admin.py
├── exceptions.py
├── models.py
├── services.py
└── tests/
```
