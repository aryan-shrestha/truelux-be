# Running the shop

Status: Current

Last updated: 2026-09-23

---

## Who this is for

You run the shop. Everything here is done in the admin at `/admin/`, and nothing
here needs a developer.

Three things in this shop **do not fix themselves, and nothing warns you when they
go wrong**. They are not bugs. They are consequences of how the shop was built, and
each one is recoverable in a few clicks — but only by someone who knows to look.
That is what the first section is about. Read it before you open the shop, not
after the first complaint.

---

## Before you open the shop

Do these once, in this order.

### 1. Fill in your sizes and colours

A product cannot have anything to sell until these two lists exist.

- **Catalog → Sizes** — add every size you stock: S, M, L, and so on. The
  *sort order* number controls the order they appear in; small numbers come first.
- **Catalog → Colors** — the same, for colours.

Until both lists have rows, you cannot create a single sellable item. On a brand
new shop these tables start empty.

### 2. Clear your Khalti transaction limit

A new Khalti merchant account has a **Rs. 200 cap on each transaction**. Almost
every order will be larger than that, so almost every Khalti payment will fail
until the cap is lifted.

Lifting it means completing KYC verification in your Khalti dashboard and then
contacting Khalti support to ask for the limit to be removed. Do this before your
first real sale, not after the first customer cannot pay.

### 3. Decide who gets a staff account

Anyone with a staff account can do **everything**: cancel orders, change stock, and
read every customer's home address and phone number. There are no limited roles —
an account either has full access or none.

Give staff accounts only to people you would trust with the whole shop.

---

## The three things you must check regularly

### Every day: release stock held by abandoned orders

**What happens.** When a customer places an order, the shop immediately sets their
items aside — before they have paid. That is deliberate: it stops two people buying
the last shirt. But a customer who goes to Khalti and then closes the tab leaves an
order that will never be paid, still holding those items. Nothing releases them.

**What it looks like.** An item shows as out of stock, or nearly out, while orders
sit unpaid for days.

**What to do.**

1. Go to **Orders → Orders** and filter Status to **Pending**.
2. Look at the ones created more than a day ago. A customer who was going to pay
   has normally paid within minutes. A pending order from yesterday is almost
   always abandoned — but check the payment first, below, in case they paid and the
   shop did not notice.
3. Select the genuinely abandoned ones and run **Cancel selected orders and return
   their stock**.

The items go straight back on sale. Cash-on-delivery orders are different: those
are not waiting on a payment, so do not cancel them for being unpaid.

### Every day: check for payments the shop missed

**What happens.** Khalti does not tell the shop about a payment. The shop only
finds out because the customer's browser comes back from Khalti. If the customer
pays and then closes the tab, or their connection drops on the way back, **the
money is taken and the shop still thinks the order is unpaid**.

Nothing detects this. Not ever, unless you look.

**What it looks like.** A customer says they paid. The order says Pending. Both are
true.

**What to do.**

1. Go to **Payments → Payments** and filter Status to **Pending**, Method to
   **Khalti**.
2. Select all of them and run **Verify selected payments with Khalti**.

The shop asks Khalti directly what happened to each one. Anything Khalti confirms
as paid is marked paid and its order moves on. Anything else is left alone. It is
safe to run on a payment that was already verified, and safe to run on the whole
page — cash-on-delivery payments are skipped and the shop tells you how many.

Do this before cancelling anything as abandoned.

### When a customer says they got no email: resend it

**What happens.** Each email is sent once. If it fails — the customer's mail server
was down, the address had a typo — **nothing tries again**, and nothing tells you it
failed.

This matters more than it sounds. The confirmation email contains the customer's
only link back to their order. There are no customer accounts, so if that email
never arrives, they have no way to see their own order.

**What to do.**

- Go to **Orders → Orders**, find the order, select it, and run **Resend the
  confirmation email** or **Resend the shipping notice**.
- The shop tells you which ones sent and which failed.

**The email always goes to the address on the order.** You cannot redirect it to a
different address, and that is on purpose: the email carries a link that opens the
order, so anyone who received it could see that customer's details. If the address
on the order is wrong, correct it on the order first, then resend.

---

## Day-to-day

### Taking an order through to delivery

In **Orders → Orders**, select the order and run the action for what just happened:

| Action | When |
| --- | --- |
| **Mark selected orders as paid** | Rarely. For cash on delivery use the payments action below instead, so the payment record agrees with your takings |
| **Mark selected orders as shipped** | Handed to the courier. **This emails the customer.** |
| **Mark selected orders as delivered** | Courier confirmed delivery |
| **Cancel selected orders and return their stock** | Abandoned or cancelled by the customer |

You cannot edit an order's status directly, only through these actions. That is
deliberate: the actions also move stock and send email, and typing a status into
the box would skip all of it.

Orders only move forward through the sequence. If an action is refused, the shop
tells you why.

### Collecting cash on delivery

When the courier hands you the cash for a cash-on-delivery order:

1. Go to **Payments → Payments**.
2. Select that order's payment and run **Mark cash as collected on selected
   payments**.

This marks the payment collected and the order paid, in one step. Do not mark the
order paid directly — the payment record would stay unpaid and your payment list
would stop matching your takings.

### Adding a product

1. **Catalog → Products → Add**, fill in the details, and save.
2. Select the product and run **Generate variants for the selected products**. Pick
   the sizes and colours you stock it in, and the shop creates every combination
   with its own code. It skips any that already exist, so it is safe to run again
   after adding a new colour.
3. Every new item starts at **zero stock**. Select the ones you have and run
   **Adjust stock for the selected variants** to set the real count.

Stock cannot be typed in directly, only set through that action — it is the only
way the shop can be sure two people are not changing the same number at once.

### Product photos

Removing a photo from a product removes it from the shop, but **the image file
itself stays on the image service**. It is no longer shown anywhere, and it does
not cost you anything to leave, but assume it still exists.

If a photo is simply wrong, replace it rather than deleting it.

---

## What the shop cannot do

Worth knowing before a customer asks.

- **Refunds** are done in your Khalti dashboard, not here. The shop will show a
  refunded payment as refunded, but it will not change the order by itself — cancel
  the order here as well, so your records agree.
- **There are no customer accounts.** Customers reach their order only through the
  link in their email. There is no login and no order history.
- **Nothing is scheduled.** Every check in this document happens because a person
  does it. The shop has no way to run anything on a timer.

---

## When something is wrong and this document does not cover it

Write down the order number, what you expected, and what you saw, and send it to
whoever maintains the shop. The order number is the fastest way for them to find
everything else.
