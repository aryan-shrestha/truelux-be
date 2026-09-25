# Transactional email

Status: Implemented

Last updated: 2026-09-25

---

## Goal

Tell the customer their order was received, and tell them when it ships — inside
the request that caused it, because there is no task queue to defer to.

---

## Scope

What is included in this implementation?

- A domain-agnostic `send_email` in `apps/core/email.py`
- Order confirmation and order shipped emails, with HTML and plain-text bodies
- `transaction.on_commit` registration at both trigger points
- `STOREFRONT_URL`, which the confirmation link needs
- Resend actions in the admin, which are the only recovery mechanism

What is explicitly outside the scope?

- An outbox table, a retry mechanism, or any queue
- Marketing email, newsletters, or subscription management
- Abandoned-cart email, which needs a persisted cart
- Delivery tracking, open tracking, or bounce handling
- SMS or Viber notification

---

## Context

[ADR 0006](../decisions/0006-transactional-email-sends-in-request-on-commit.md) is
the governing decision. Email is registered with `transaction.on_commit`, failures
are caught and logged at `ERROR`, and nothing is retried.

`architecture.md` forbids a task queue and states that every unit of work completes
inside the request that started it. It says nothing about email, which is why that
ADR exists.

Two things make a failed email more serious here than in a typical store:

- Under [ADR 0003](../decisions/0003-guest-checkout-with-opaque-order-access-tokens.md),
  the confirmation email carries the order's `access_token`. It is the customer's
  only route back to their order. A failed send means a customer who cannot reach
  their own purchase.
- Under [ADR 0002](../decisions/0002-admin-writes-go-through-the-service-layer.md),
  the shipping email is triggered by a service called from an admin action. If a
  merchant's status change bypassed the service, no email would send at all — which
  is why `status` is read-only in the admin form.

`config/settings/base.py` configures `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, the
SMTP block and `EMAIL_TIMEOUT` — the last because ADR 0006 sends inside the
request, so an unresponsive SMTP host would otherwise hold a gunicorn worker open
indefinitely. `local.py` sets a console backend and `test.py` a `locmem` one.

The configuration was in place before this feature started; what it added was the
sending — `apps/core/email.py`, the order emails, and the templates.

---

## Planned

The intended implementation:

- `apps/core/email.py`: `send_email(*, to, subject, template_name, context)`,
  rendering an HTML and a text template, catching broadly, logging at `ERROR`, and
  never raising. It imports nothing from a domain app
- `apps/orders/emails.py`: `send_order_confirmation(*, order)` and
  `send_order_shipped(*, order)`, owning subjects, templates, and context
- Templates under `apps/orders/templates/orders/email/`
- `transaction.on_commit` registration inside `place_order` and
  `mark_order_shipped`
- ~~`EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, and SMTP settings in
  `config/settings/base.py`~~ — already present, added with ADR 0006's
  `EMAIL_TIMEOUT`
- ~~`locmem` backend in `config/settings/test.py`~~ — already present
- Resend actions on `OrderAdmin`

---

## Implemented

- `apps/core/email.py` — `send_email`, rendering a text body and an HTML
  alternative, **catching everything and never raising**. Returns whether it sent,
  so a caller reporting to a human can say. Its `reference` argument is what the
  log line identifies the message by, since the recipient may not be logged
- `apps/orders/emails.py` — `send_order_confirmation` and `send_order_shipped`,
  owning subjects, templates and context
- Seven templates under `apps/orders/templates/orders/email/`: a `.txt` and a
  `.html` for each message, plus a shared HTML base and two includes
- `transaction.on_commit` inside `place_order` and inside `_transition` when the
  new status is `shipped` — in the services, not their callers
- Two resend actions on `OrderAdmin`, which are the only recovery a failed send has
- `STOREFRONT_URL`, the storefront root the link is built from
- TrueLux branding: a "TrueLux" header on the HTML base, a sign-off on the text
  bodies, and subjects "TrueLux order <number> received" and "Your TrueLux order
  <number> is on its way". The confirmation says the shop will call to confirm and
  that the customer pays the courier in cash (ADR 0011). Line items show the shade
  only when the variant has one.
- `apps/core/tests/test_email.py` and `apps/orders/tests/test_emails.py` — 23 tests

---

## Remaining

- **No provider account is configured.** `local.py` prints to the console and
  `test.py` uses `locmem`, so nothing here needs one; production needs
  `DJANGO_EMAIL_BACKEND`, `EMAIL_HOST` and credentials pointed at a real relay
  before a customer receives anything. That is four values in `.env`, no code.
- **No email has been seen rendered by a real client.** The templates are checked
  by tests and readable in the console backend, but nothing has looked at them in
  Gmail or Outlook, where support for even inline CSS varies.
- The styling is deliberately plain — one table, inline styles, no images.

---

## Decisions

### Decision: the mechanism lives in `core`, the content lives in `orders`

**Decision**

`apps/core/email.py` knows how to render and send. `apps/orders/emails.py` knows
what to say and when.

**Reason**

`architecture.md` forbids `core` from importing any domain app. A `send_order_email`
in `core` would violate that, and `core` would then need to know what an `Order` is.

**Consequence**

Any future email — a password reset, a restock notice — reuses the mechanism
without touching orders. If an outbox is ever added, it goes in `core` too, and
`apps/notifications` becomes a real app only when it owns a table.

### Decision: the send is registered inside the service, not called from the view

**Decision**

`place_order` and `_transition` register the callback themselves.

**Reason**

Putting it in the view means every caller has to remember. The admin action would
not, so a merchant marking an order shipped would send nothing — exactly the bug
ADR 0002 exists to prevent. `convention.md` also places logging and side effects at
the service layer, where the state change happens.

**Consequence**

Services have an observable side effect beyond their return value, which tests must
account for. `test_confirmation_is_sent_after_commit` needs
`django_capture_on_commit_callbacks`, or it will assert against an empty outbox and
pass for the wrong reason.

---

## Gotchas

- **`transaction.on_commit`, never a direct call inside `atomic()`.** An SMTP
  timeout inside the transaction rolls back a placed order. This is the entire
  reason the decision exists.
- **Tests will silently not send.** `on_commit` callbacks do not run inside
  `pytest.mark.django_db`'s transaction unless wrapped in
  `django_capture_on_commit_callbacks(execute=True)`. A test asserting
  `len(mail.outbox) == 1` without it fails; a test asserting `== 0` passes and
  proves nothing.
- **Never log the recipient's full email address.** `convention.md`'s never-log
  list is explicit. Log the order id.
- **Never log or template the `access_token` anywhere except the link itself.** It
  is a credential. It must not appear in the plain-text fallback as a bare string,
  and the link must be HTTPS.
- A failure is invisible to everyone: the customer sees a successful order page, and
  the merchant sees nothing. The only trace is an `ERROR` line. Nothing alerts.
- SMTP occupies a gunicorn worker for the duration of the send, in the same way an
  image upload does. On Render's smaller instances this is a real concurrency cost.
- `local.py` already sets the console backend. Do not remove it — it is what makes
  local development work without credentials.
- **Rendering happens inside `send_email`'s `try`, not before it.** A
  `TemplateSyntaxError` or a missing attribute raised while building the message
  would otherwise escape the `on_commit` callback — and the transaction has already
  committed by then, so the customer would get a 500 for an order that was placed
  and whose stock is gone. The review found this; `test_a_template_failure_does_not_fail_checkout`
  pins it, separately from the send-failure test, because mocking `.send()` does
  not reach the rendering.
- **`send_email` strips the text body.** A template opening with a tag renders a
  leading blank line, and the customer reads the result. Stripped in the mechanism
  rather than in each template, so the next one cannot reintroduce it.
- **Both parts of a multipart message must say the same thing.** `_items.html`
  is shared by both emails and takes `show_prices`, because the shipped email's
  text part lists no prices. Included without it, the HTML part listed them and
  the same message said two different things depending on the client.
- **Item prices are unit prices, labelled "each".** `OrderItem` stores
  `unit_price` and no line total, so an unlabelled figure beside "2 x" reads as
  a line total and the receipt visibly fails to add up to the subtotal.
- **The `.txt` templates wrap everything in `{% autoescape off %}`.** Django
  escapes plain-text templates like any other, so without it a customer called
  "Ben & Jerry" is greeted as "Ben &amp; Jerry".
- The confirmation's `access_token` appears **exactly once** in the text body, and
  only inside the URL. `test_the_access_token_appears_only_inside_the_link` counts
  it: bare in the body, it is something a customer might paste into a support chat
  without knowing what it is.
- Only the **shipped** transition sends. Confirmed and delivered are not customer-facing
  events, and `test_no_email_is_sent_for_the_other_transitions` says so, so adding
  one later is a deliberate change rather than an accident.

---

## API

None. This feature adds no endpoints.

---

## Data changes

None. ADR 0006 explicitly rejects an outbox table for Phase 1.

---

## Permissions

No API surface. The resend actions in the admin require `is_staff`.

One consequence worth stating: the resend action re-delivers an email containing the
order `access_token` to the address stored on the order. It cannot be redirected to
a different address, and it must not be made to accept one — that would turn a
support tool into a way to steal an order.

---

## Tests

23 tests. Every one that asserts on the outbox uses
`django_capture_on_commit_callbacks(execute=True)`; without it a callback never
runs inside `pytest.mark.django_db`'s transaction, and an assertion of `== 0`
passes while proving nothing.

`apps/core/tests/test_email.py`:

- `test_send_email_renders_html_and_text_bodies`
- `test_the_text_body_has_no_leading_blank_line` and
  `test_the_text_body_is_not_html_escaped` — what the customer actually reads,
  which no other assertion looks at
- `test_send_email_swallows_backend_failure`
- `test_send_email_swallows_a_template_failure` — the rendering half of the
  failure surface, which mocking `.send()` does not reach
- `test_send_email_logs_failure_at_error_level`
- `test_send_email_does_not_log_recipient_address` and
  `test_send_email_does_not_log_the_recipient_on_success`
- `test_both_templates_render` — parametrised

`apps/orders/tests/test_emails.py`:

- `test_confirmation_is_sent_after_commit`
- `test_confirmation_is_not_sent_before_the_transaction_commits`
- **`test_confirmation_is_not_sent_when_transaction_rolls_back`** — the test that
  proves ADR 0006 holds. If it starts failing, someone moved the send inside the
  transaction and an SMTP timeout can now destroy a placed order
- `test_confirmation_contains_order_access_link`
- `test_the_access_token_appears_only_inside_the_link`
- `test_a_multi_unit_line_says_the_price_is_per_unit` and
  `test_the_shipped_email_parts_agree_about_prices` — every other email test
  places a single unit, so both defects they pin were invisible to the suite
- `test_shipped_email_is_sent_by_the_service_not_the_admin`
- `test_no_email_is_sent_for_the_other_transitions`
- `test_email_failure_does_not_fail_checkout` and
  `test_a_template_failure_does_not_fail_checkout`
- `test_resend_confirmation_action_sends_to_the_address_on_the_order`,
  `test_resend_shipping_notice_action_sends`,
  `test_a_failed_resend_is_reported_to_the_merchant`

---

## Files

```text
apps/core/
├── email.py
└── tests/
    └── test_email.py
apps/orders/
├── emails.py
├── admin.py                          the two resend actions
├── services.py                       the two on_commit registrations
├── templates/orders/email/
│   ├── _base.html                    shared shell, inline styles only
│   ├── _items.html                  takes show_prices; see Gotchas
│   ├── _address.html
│   ├── order_confirmation.html
│   ├── order_confirmation.txt
│   ├── order_shipped.html
│   └── order_shipped.txt
└── tests/
    └── test_emails.py
config/settings/base.py               STOREFRONT_URL
config/settings/test.py
.env.example
apps/payments/client.py               the rename
apps/payments/views.py                the rename
```

---

## Future context

`test_confirmation_is_not_sent_when_transaction_rolls_back` is the test that proves
the decision holds. If it starts failing, someone has moved the send inside the
transaction and a placed order can now be destroyed by an SMTP timeout.

The accepted failure mode — an order with no confirmation email, no retry, and
therefore a customer with no access token — is the most likely source of real
support load in Phase 1. The resend action is written up for the merchant in
[../handover.md](../handover.md#when-a-customer-says-they-got-no-email-resend-it),
including why it cannot be redirected to another address.

The upgrade path is an outbox table in `core` plus an externally triggered drain
endpoint. ADR 0004 needs the same external trigger to release stale stock and
ADR 0005 needs it to reconcile stranded payments. Three decisions converge on one
missing mechanism; when it is built, build it once and serve all three.
