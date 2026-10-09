# Inventory

Status: Implemented

Last updated: 2026-10-09

---

## Goal

Answer *why* a variant's stock changed and *who* changed it, and let staff record
deliveries and losses without overwriting sales made in the meantime.

---

## Scope

Included:

- A new `apps/inventory` app that owns every write to
  `ProductVariant.stock_quantity`
  ([ADR 0019](../decisions/0019-stock-changes-are-a-ledger-in-the-inventory-app.md))
- An immutable `StockMovement` ledger, written in the same locked transaction as
  each stock change
- Relative adjustments with a reason: `received`, `returned`, `damaged`,
  `expired`, `tester`, `correction`
- Absolute counts recorded as a `stocktake`, with the variance as the change
- Staff attribution: services take an explicit `actor`
- Admin API: `POST variants/{id}/stock-adjustments/` and `GET stock-movements/`
- A read-only ledger in the Django admin

Outside the scope:

- Reservations: on-hand and committed stock are still one figure
- A returns flow after delivery. Staff record returned goods as a `returned`
  adjustment
- Batches, expiry, cost and valuation, suppliers and purchase orders, locations
- Per-variant reorder points

---

## Context

### Stock model

`ProductVariant.stock_quantity` (`apps/catalog/models.py`) is still the balance
that checkout locks and reads. `CheckConstraint
product_variant_stock_not_negative` keeps it at 0 or above. `OrderItem.variant`
is `PROTECT`. The ledger explains the balance; it does not replace it.

### Order lifecycle

```text
place_order ──(sale)──> pending ──> confirmed ──> shipped ──> delivered
                           │             │
                           └──> cancelled <┘   (cancellation)
```

Stock is committed when the order is placed (ADR 0004). Confirming, shipping and
delivering do not move stock. Cancelling is allowed only from `pending` or
`confirmed`, and it returns the stock. Pending orders never expire.

### Reads that were not changed

- Public API: `in_stock` only, never the count. `InsufficientStock` leaves out
  the available count (`catalog-browsing.md`).
- Admin API: `stock_quantity` on variants, `total_stock` on products,
  `low_stock=true` and the dashboard's `low_stock` list (threshold 5 in
  `apps/backoffice/constants.py`).

---

## Implemented

- `apps/inventory/models.py` — `StockMovement` with `variant` (`SET_NULL`) and a
  `sku` snapshot, `reason`, `quantity_change`, `balance_after`, `order`
  (`SET_NULL`), `actor` (`SET_NULL`) and `note`. `MovementReason`, plus
  `INCREASING_REASONS`, `DECREASING_REASONS` and `MANUAL_REASONS`.
  Three named CHECK constraints: the reason is valid, the balance is at least 0,
  and the direction matches the reason.
- `apps/inventory/services.py` — the stock services moved here from
  `apps/catalog/services/stock.py`. Each one writes movements:

  | Service | Movement | Caller |
  | --- | --- | --- |
  | `decrement_variant_stock(quantities=, order_id=)` | `sale`, one per variant, linked to the order | `orders.services.place_order` |
  | `restore_variant_stock(quantities=, order_id=, actor=)` | `cancellation`, linked to the order | `orders.services.cancel_order` |
  | `set_variant_stock(variant=, quantity=, actor=, note=)` | `stocktake`, change = new − old, may be 0 | Django admin **Adjust stock**, `update_variant` (admin API PATCH), `create_variant` (opening stock), workbook import |
  | `adjust_variant_stock(variant=, quantity_change=, reason=, actor=, note=)` | the given manual reason | `POST /api/v1/admin/variants/{id}/stock-adjustments/` |
  | `check_variant_availability(quantities=)` | none (read only) | `orders.services.quote_cart` |

- `apps/inventory/exceptions.py` — `InvalidStockAdjustment`: 400
  `validation_error`, with `details.quantity_change`.
- `apps/inventory/admin.py` — `StockMovementAdmin`: list, filter and search
  only. No add, change or delete.
- `apps/catalog/services/products.py` — `create_variant` and `update_variant`
  take `actor`. Opening stock goes through `set_variant_stock`, noted "Opening
  stock".
- `apps/orders/services.py` — `place_order` generates the order UUID up front
  and passes it to the decrement. `cancel_order(order=, actor=)` and
  `transition_order(order=, to=, actor=)` take the actor; only cancelling uses
  it.
- `apps/backoffice/` — `VariantStockAdjustmentView`, `StockMovementListView`,
  `StockAdjustmentSerializer`, `StockMovementSerializer`,
  `AdminStockMovementFilter`, `selectors.list_stock_movements`. Variant
  create/PATCH and order transitions pass `request.user` as the actor.
- `apps/catalog/admin.py`, `apps/orders/admin.py` — the Adjust stock and Cancel
  actions pass the signed-in user.
- `apps/catalog/workbook/importer.py` — stock is set with `actor=None` and
  `note=IMPORT_NOTE` ("Catalogue workbook import").

---

## Remaining

Not started; each needs its own decision:

- Reservations: separate on-hand from committed stock
- A returns flow after delivery (delivered → returned, then restock or write
  off)
- Batches with expiry dates
- Per-variant reorder points. The low-stock threshold is still global and still
  counts unpublished products.
- Bulk **Adjust stock** in the Django admin still applies one count to every
  selected variant
- `seed_demo` writes stock with `bulk_create` and records no movements (demo
  data only)
- The admin app (front end) does not use the adjustment or ledger endpoints yet.
  `handover.md` still tells the merchant that stock is always the counted total,
  which is true of the variant form.

---

## Decisions

### Decision: the ledger records changes; the column stays the balance

**Decision**

`stock_quantity` remains the source of truth for availability. Every change to it
writes a `StockMovement` in the same transaction.

**Reason**

Checkout's single-row lock (ADR 0004) and every existing read keep working. A
balance computed from `SUM()` would need an aggregate and a different lock.

**Consequence**

The two can only drift if something writes `stock_quantity` outside
`apps/inventory/services.py`. Nothing may.

### Decision: manual changes are relative; counts are stocktakes

**Decision**

Deliveries and losses go through `adjust_variant_stock`, a delta under the row
lock. An absolute count is a `stocktake` whose change is the variance.

**Reason**

An absolute write overwrites a sale made between reading the figure and saving
it. A delta cannot.

**Consequence**

The variant PATCH `stock_quantity` and the workbook import are still absolute.
Their variance is visible in the ledger, but they can still overwrite a
concurrent sale.

---

## Gotchas

- `place_order` passes an `order_id` that has not been inserted yet. This works
  because Django creates Postgres foreign keys `DEFERRABLE INITIALLY DEFERRED`.
  Changing that would break checkout.
- Deleting a variant, an order or a user sets that foreign key to null on its
  movements. Use `sku` to read old history.
- A `stocktake` may have `quantity_change = 0`, meaning a count that confirmed
  the figure. No other reason may.
- `adjust_variant_stock` raises `ValueError` (a programming error, so a 500) for
  `sale`, `cancellation` or `stocktake`. The API serializer only offers
  `MANUAL_REASONS`.
- Variant locks are always taken in ascending `pk` order with `of=("self",)`
  (ADR 0004).
- Log event names stayed `catalog.stock_*`; `adjust_variant_stock` logs
  `inventory.stock_adjusted`.

---

## API

See `admin-api.md` for the adjustment and ledger endpoints, their bodies and the
movement representation.

---

## Data changes

- `apps/inventory/migrations/0001_stock_movement.py` — creates the
  `stock_movement` table, its three CHECK constraints, and indexes on the foreign
  keys and on `created_at`. It is additive: no existing table changes, and stock
  held before the migration has no opening movement.

---

## Permissions

Admin API endpoints use `StaffAPIView` (JWT, active staff). The Django admin
ledger is visible to staff with view permission and cannot be edited by anyone.

---

## Tests

- `apps/inventory/tests/test_ledger.py` — sales are linked to the order (also
  through `place_order`); cancellations record the actor; stocktake variance,
  including 0; adjustments are relative and keep a concurrent sale; direction
  rules; cannot go below zero; corrections go either way; order reasons are
  refused; opening stock is a stocktake; history survives deleting the variant;
  the database refuses a contradictory row.
- `apps/inventory/tests/test_services.py` — the moved lock, availability and
  oversell tests.
- `apps/backoffice/tests/test_stock.py` — adjustment endpoint, field errors,
  ledger list and filters, PATCH recorded as a stocktake.
- `apps/backoffice/tests/test_permissions.py` — covers the new routes
  automatically.
- Still guarding concurrency:
  `apps/orders/tests/test_checkout.py::test_concurrent_checkout_for_last_unit_places_one_order`,
  `apps/catalog/tests/test_admin.py::test_a_restock_and_a_sale_do_not_interleave`,
  `apps/orders/tests/test_services.py::test_concurrent_cancellation_restores_the_stock_only_once`.

---

## Files

```text
apps/inventory/
├── apps.py
├── models.py
├── exceptions.py
├── services.py
├── admin.py
├── migrations/0001_stock_movement.py
└── tests/{test_ledger,test_services}.py
apps/catalog/services/products.py     create_variant, update_variant (actor)
apps/catalog/workbook/importer.py     IMPORT_NOTE
apps/orders/services.py               place_order, cancel_order, transition_order
apps/backoffice/{views,serializers,filters,selectors,urls}.py
```

---

## Future context

A reservation model would add a `committed` figure and move the `sale` movement
from placement to shipping. That reverses ADR 0004's "committed at placement" and
needs its own ADR.
