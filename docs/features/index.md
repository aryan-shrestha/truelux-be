# Features

Current feature inventory.

Phase 1 turns a social-media-only clothing brand into a store. Checkout is
guest-only, payment is cash on delivery or Khalti, and the Django admin is the
merchant's entire back-office.

| #   | Feature             | Status  | Documentation                     | Depends on | Last updated |
| --- | ------------------- | ------- | --------------------------------- | ---------- | ------------ |
| 1   | staff-identity      | Implemented | `features/staff-identity.md`  | —          | 2026-09-23   |
| 2   | api-error-contract  | Implemented | `features/api-error-contract.md` | 1      | 2026-09-21   |
| 3   | media-storage       | Implemented | `features/media-storage.md`   | —          | 2026-09-20   |
| 4   | product-catalog     | Implemented | `features/product-catalog.md` | 2, 3       | 2026-09-20   |
| 5   | catalog-browsing    | Implemented | `features/catalog-browsing.md` | 4      | 2026-09-21   |
| 6   | orders              | Implemented | `features/orders.md`          | 2, 4       | 2026-09-21   |
| 7   | checkout            | Implemented | `features/checkout.md`        | 6          | 2026-09-21   |
| 8   | payments            | Implemented | `features/payments.md`        | 7          | 2026-09-21   |
| 9   | transactional-email | Implemented | `features/transactional-email.md` | 6, 8   | 2026-09-23   |
| 10  | merchant-admin      | Implemented | `features/merchant-admin.md`  | 4, 6, 8    | 2026-09-22   |
| 11  | demo-seed           | Implemented | `features/demo-seed.md`       | 4, 6, 8    | 2026-09-24   |
| 12  | deployment          | Implemented | `features/deployment.md`      | —          | 2026-09-24   |

`Depends on` refers to the `#` column of this table.

## Implementation order

Implement in table order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10.

`demo-seed` (#11) sits outside that order: it is a development tool, not part of
the product, and it was added when the storefront repository found that a fresh
database serves an empty catalogue and nothing can be built against it.
`deployment` (#12) sits outside it too, for the obvious reason.

`staff-identity` is first because nothing else could run until it landed: the
URLConf imported an `apps/users` API surface that no longer exists, so no server,
no test and no migration would start. That surface has been removed and the
project boots.

`api-error-contract` carried the published error-code map and its tests, and stayed
In progress until a real `DomainError` subclass reached a client. `checkout` (#7)
did that: `VariantUnavailable` and `InsufficientStock`, defined by `product-catalog`
and raised by `apps.catalog.services`, are now returned as 422s by
`POST /api/v1/checkout/` and asserted there. It is Implemented.

`catalog-browsing` is the first feature with an HTTP surface, and it found that
`convention.md`'s "let `DoesNotExist` propagate; the handler returns 404" was not
true of the handler — an unknown slug would have been a 500. The handler now maps
`ObjectDoesNotExist`. Every later selector depends on this, `orders` most of all.

**Both payment methods work end to end.** Cash on delivery records what the
courier will collect; Khalti initiates at checkout, and the return endpoint
verifies with a server-to-server lookup before anything is fulfilled.
`docs/integrations/khalti.md` transcribes the upstream contract that was written
against — read it before changing `apps/payments/client.py`.

**Khalti needs credentials before anything will start.** Under
[ADR 0008](../decisions/0008-every-environment-variable-is-required.md) every
environment variable is required in every environment, so a developer needs Khalti
values in `.env` even to run the catalogue tests — a placeholder key boots, only a
real one takes a payment. The sandbox path has not been walked end to end; every
test stubs Khalti at the HTTP boundary.

**The storefront now owes two routes**: `/orders/<access_token>` and
`/orders/failed?reason=<code>`, which is where the payment return redirects. That
is a contract between the two repositories and nothing in this one enforces it.

**Every Phase 1 feature is implemented.** A customer can browse the catalogue,
place an order, pay by cash or Khalti, and receive a confirmation carrying the only
link back to their purchase. A merchant can run the shop from the Django admin.

One thing is not done, and it is not a feature:

- **No write path has run against real infrastructure.** The Supabase project is
  migrated and holds the `demo-seed` catalogue — 9 products, 37 variants, 6
  categories — so the read paths have real data behind them. Nothing else does:
  `users` has no rows, so **no superuser exists and the admin has never been
  opened**; `order` and `payment` are empty; the Khalti sandbox path is unwalked;
  and no email has been seen in a real client. Every claim about a write in these
  documents rests on the test suite, including every workflow
  [../handover.md](../handover.md) describes. That Supabase project is shared
  development, not production — production will be a separate project, so the demo
  catalogue in it is expected rather than something to clean up.

[../handover.md](../handover.md) is the merchant's document, and the only one
written for someone who is not an engineer. It carries the three standing duties
that no automation covers — review pending orders so held stock is released,
verify stranded payments, and resend failed emails — each a failure mode with no
automatic recovery and no alert. `merchant-admin.md`, `transactional-email.md`,
`media-storage.md` and ADR 0004 each link to the section that carries theirs.

`checkout` (#7) creates the order, `payments` (#8) records what is owed on it, and
`transactional-email` (#9) sends the customer the link that is their only route
back to it. That link is `{STOREFRONT_URL}/orders/<access_token>` — the same page
the Khalti return redirects to, so the storefront owes one route, not two.

`api-error-contract` (#2) closes here: `VariantUnavailable` and `InsufficientStock`
now reach a client as 422s through `POST /api/v1/checkout/`, which is the condition
it was waiting on.

**`size` and `color` ship empty, and a `ProductVariant` cannot be created until
both hold rows** — per
[ADR 0007](../decisions/0007-size-and-colour-are-lookup-tables.md) they are lookup
tables. `SizeAdmin` and `ColorAdmin` landed with `merchant-admin` (#10), so on a
fresh production database the merchant's first task is to fill them. The handover
document says so.

For **development**, `demo-seed` (#11) still fills them along with a demo
catalogue: `make seed`. It refuses to run outside `DEBUG`. Its reason for existing
narrowed when #10 landed, from "nothing can populate these" to "give a developer
something to look at", which is a smaller claim but still a useful one.

**Read `merchant-admin.md` before writing any `admin.py`.** ADR 0002 constrains
every admin module in the repository. Authoring that document before the code was
written is why nothing had to be rewritten when the four modules landed.

**The merchant can now run the shop.** Sizes and colours are enterable, variants
are generated rather than typed, stock is adjustable through a locked service,
orders move through their lifecycle by action, and both payment recoveries exist.
What remains shell-only is nothing.

## Architectural decisions

Eight decisions in `docs/decisions/` govern this phase. Read the relevant one before
implementing the feature that depends on it.

| ADR  | Decision                                    | Governs                              |
| ---- | ------------------------------------------- | ------------------------------------ |
| 0001 | The variant is the stock and SKU unit       | product-catalog, orders, checkout     |
| 0002 | Admin writes go through the service layer   | merchant-admin, every `admin.py`      |
| 0003 | Guest checkout, with opaque access tokens   | orders, checkout, staff-identity      |
| 0004 | Stock is committed at order placement       | checkout, product-catalog, orders     |
| 0005 | Khalti lookup is the only verification      | payments                              |
| 0006 | Transactional email sends in-request        | transactional-email, checkout         |
| 0007 | Size and colour are lookup tables           | product-catalog, merchant-admin       |
| 0008 | Every environment variable is required      | every app; `config/settings`          |

## Integration references

`docs/integrations/` transcribes the published API contracts of external systems,
so an implementation is written against a fixed document rather than a
recollection of one. [khalti.md](../integrations/khalti.md) carries Khalti's
ePayment (KPG-2) documentation — the initiate payload, the callback parameters,
every lookup status with its HTTP code, and the error bodies. Read it before
writing the Khalti client for `payments` (#8). ADR 0005 records what this
repository does about that contract; it is not a substitute for the contract.

## Deferred to Phase 2 and later

Customer accounts and order history, discount codes, wishlist, abandoned-cart
email, product reviews, returns and refunds in-app, multi-currency, gift cards, a
custom merchant dashboard, courier tracking, faceted search, and restock
notifications.

Three Phase 1 decisions each accept a failure mode with no automatic recovery —
stale held stock (ADR 0004), stranded payments (ADR 0005), and unsent email
(ADR 0006). All three are resolved by the same mechanism: an external scheduler
calling an authenticated sweep endpoint. When that is built, build it once.

## Status definitions

- **Planned** — documented but implementation has not started.
- **In progress** — implementation has started but is incomplete.
- **Implemented** — documented scope is implemented and verified.
- **Blocked** — implementation cannot continue because of a documented blocker.
- **Deprecated** — feature exists but should not receive new development.
