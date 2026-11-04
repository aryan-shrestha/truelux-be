# ADR 0019: Stock changes are a ledger in the inventory app

Status: Accepted

Date: 2026-10-09

Supersedes: the "no stock-movement ledger" part of
[ADR 0001](0001-variant-is-the-stock-and-sku-unit.md)

---

## Context

ADR 0001 kept stock as one integer per variant with no history, and named the
trigger for revisiting that: "when the merchant needs to answer *why* stock
changed, not just what it is". The merchant now needs that answer. The only
record of a stock change was a structured log line. The lines for sales and
cancellations carried only a variant count, and none of them said who made the
change or why.

Manual edits were also absolute counts. The row lock serialised the write, but
not what the staff member had read beforehand, so a sale made while they were
typing was overwritten. The workbook import did the same across the whole period
between export and import.

## Decision

A new `inventory` app owns **every write to `ProductVariant.stock_quantity`** and
an immutable `StockMovement` ledger. The services that were in
`apps/catalog/services/stock.py` moved to `apps/inventory/services.py`, unchanged
except that each one now writes a movement row in the same locked transaction as
the stock change.

- `stock_quantity` stays as the running balance and is still what checkout locks
  and reads (ADR 0004 unchanged). The ledger explains the balance; it does not
  replace it.
- Each movement records `reason`, `quantity_change`, `balance_after`, `sku`
  (a snapshot), and optionally the `order`, the staff `actor` and a `note`.
- Reasons: `sale` and `cancellation` come only from orders. `stocktake` is an
  absolute count whose change is the variance, and may be 0. `received`,
  `returned`, `damaged`, `expired`, `tester` and `correction` are relative
  adjustments staff make through `adjust_variant_stock`.
- A `CheckConstraint` ties the direction of each change to its reason, and
  another keeps `balance_after >= 0`.
- Services take an explicit `actor: User | None`. Views pass `request.user`.
  The storefront and management commands pass `None`.
- All three foreign keys are `SET_NULL`, so deleting a variant, an order or a
  user keeps the history readable through the `sku` snapshot.

## Reason

A ledger written in the same transaction as the stock change cannot drift from
it. A ledger written anywhere else can. Keeping `stock_quantity` as the balance
leaves checkout's single-row lock and every existing read unchanged.

Putting the ledger and the stock writes in one app keeps a single owner for
"stock changed, and here is why". The alternative was to leave the services in
`catalog` and have them write another app's table, which splits that ownership.

## Alternatives considered

### Ledger model in `catalog`

Simpler: no new app and no import moves. The user chose a separate app so that
inventory can grow (reservations, batches, locations) without crowding the
catalogue.

### Deriving stock from the ledger (`SUM(quantity_change)`)

Why it was not chosen: every availability check and checkout lock would become an
aggregate. The ADR 0004 lock would have to lock a balance that no longer exists as
a row.

## Consequences

### Positive

- "Why did this SKU change, and who did it?" is a query.
- Relative adjustments cannot overwrite a concurrent sale.
- The database refuses a movement that contradicts its reason.

### Negative

- Every stock change writes one more row. Checkout writes one per cart line.
- `place_order` generates the order's UUID before inserting it, so the sale
  movements can reference it. This depends on Django creating Postgres foreign
  keys as `DEFERRABLE INITIALLY DEFERRED`.
- `seed_demo` still writes stock with `bulk_create` and records no movements.
  That data is demo only.

### Constraints introduced

- Nothing outside `apps/inventory/services.py` writes `stock_quantity`.
  `create_variant` records opening stock through `set_variant_stock`.
- Movements are never updated or deleted. The Django admin is read-only for them.
- New stock-changing code must take variant locks in ascending `pk` order with
  `of=("self",)` (ADR 0004).

## Implementation

```text
apps/inventory/models.py       StockMovement, MovementReason, reason groups
apps/inventory/services.py     check/decrement/restore/set/adjust
apps/inventory/admin.py        read-only ledger
apps/backoffice/views.py       stock-adjustments, stock-movements endpoints
docs/features/inventory.md
```

## Future reconsideration

Reservations (on-hand versus committed), batches with expiry, and a returns flow
after delivery are the next candidates. Each adds reasons or tables here rather
than a new owner.
