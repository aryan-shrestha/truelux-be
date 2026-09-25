# ADR 0004: Stock is committed at order placement

Status: Accepted

Date: 2026-09-20

Supersedes: None

---

## Context

A customer paying with Khalti leaves the site, pays on Khalti's portal, and comes
back. Between those two moments the store has to decide whether the stock they are
buying is theirs.

Decrement at placement and two customers cannot both buy the last medium — but an
abandoned redirect holds that medium hostage. Decrement at confirmation and nothing
is held hostage — but two customers who pay simultaneously both succeed, and one of
them gets an apology instead of a shirt.

`architecture.md` makes this sharper than it would be elsewhere: there is no task
queue and no in-process scheduler. Whatever holds stock cannot be released by a
background job, because there are no background jobs. The only periodic work
possible is an external trigger calling an endpoint.

## Decision

**Stock is decremented when the order row is created**, inside the same
transaction, before the customer is redirected to Khalti.

The decrement takes a row lock on every variant in the cart:

```python
variants = ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")
```

**Locks are always acquired in `pk` order.** Two carts containing the same two
variants in opposite orders will deadlock otherwise, and Postgres resolves that by
killing one transaction.

Stock is returned to the variant when an order is cancelled. Cancellation is a
merchant action in the admin, calling
`apps.orders.services.cancel_order(...)`, which calls
`apps.catalog.services.restore_variant_stock(...)`.

**There is no automatic expiry of pending orders.** An order that was placed and
never paid holds its stock until a human cancels it.

## Reason

For a small brand, the two failure modes are not symmetrical.

Overselling is a customer-facing failure. Someone paid for a garment that does not
exist, and the merchant has to refund them and explain. It damages the thing the
website was built to establish — that this is a real store and not a DM thread.

Stuck stock is an internal failure. A few units are invisible for a few hours until
the merchant notices a pending order and cancels it. Nobody is angry. It costs
revenue only if it goes unnoticed for long enough to matter, and the admin makes it
visible.

Choosing to prevent the customer-facing failure and absorb the internal one is the
right trade at this volume. It would be the wrong trade at high volume with thin
inventory, where stuck stock compounds faster than a human can clear it.

The lock ordering is not a refinement; without it, multi-item carts deadlock under
concurrency, and the symptom is an intermittent 500 that does not reproduce.

## Alternatives considered

### Decrement on payment confirmation

Why it was not chosen: it oversells. Two customers can both pass the availability
check and both pay before either commits, and nothing in the database prevents it.
The window is small and it will still happen — small windows are exactly what
concurrency bugs live in.

### Decrement at placement with a timed release

Hold stock for fifteen minutes, then return it automatically.

Why it was not chosen: there is nothing to run the timer. No Celery, no scheduler,
no cron inside the container. Implementing it means an external service calling an
authenticated sweep endpoint on a schedule — a new deployment dependency, a new
authenticated surface, and a new failure mode where the sweeper is down and nobody
notices. That is an architectural addition, and Phase 1 does not need it.

### A reservation table separate from stock

Why it was not chosen: it is the correct design for a store with real contention,
and it is two extra tables, a join on every availability check, and the same expiry
problem this ADR is already avoiding.

## Consequences

### Positive

- Overselling is impossible. The constraint is a row lock, not a hope.
- Availability shown during browsing matches availability at checkout, because both
  read the same column.
- Cancelling an order is the only way stock returns, so stock movements have exactly
  two causes and both are greppable.

### Negative

- **An abandoned Khalti redirect holds stock indefinitely.** The customer closes the
  tab, the order sits in `pending`, and the medium is unavailable to everyone else
  until a human intervenes.
- The merchant has an ongoing operational duty: review pending orders. If they do
  not, stock silently disappears from the store. Written up for them in
  [../handover.md](../handover.md#every-day-release-stock-held-by-abandoned-orders),
  including the instruction to verify payments before cancelling anything.
- A checkout holds row locks for the duration of its transaction. Any slow work
  inside that transaction blocks other buyers of the same variants, which is why the
  Khalti initiate call happens *outside* it.

### Constraints introduced

- Locks are acquired in ascending `pk` order, always. A future service that locks
  variants in any other order reintroduces the deadlock.
- The Khalti initiate HTTP call must not happen inside the placement transaction.
  It is an external call of unbounded duration holding both a Supabase pooler slot
  and a row lock.
- `Order.status` must distinguish "placed, awaiting payment" from "paid", because
  the first holds stock and is a candidate for cancellation and the second is not.
- Stock may not go negative. A `CheckConstraint` on `ProductVariant` enforces this,
  so a service bug surfaces as a 409 rather than as silently corrupt inventory.

## Implementation

```text
apps/catalog/services.py   decrement_variant_stock, restore_variant_stock
apps/catalog/models.py     CheckConstraint stock_quantity >= 0
apps/orders/services.py    place_order (transaction boundary, lock ordering)
apps/orders/admin.py       cancel action, pending-order visibility
docs/features/checkout.md
docs/decisions/0005-khalti-lookup-is-the-only-verification.md
```

## Future reconsideration

Revisit when pending orders accumulate faster than the merchant clears them. The
first step is not a queue — it is an external cron calling an authenticated sweep
endpoint, which `architecture.md` already names as the only supported shape for
periodic work.

Revisit the placement-versus-confirmation choice itself if inventory depth grows to
where overselling is recoverable from a warehouse rather than from an apology.
