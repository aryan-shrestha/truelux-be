# Running the shop

Status: Current

Last updated: 2026-09-25

---

## Who this is for

You run TrueLux. Day to day you work in the **TrueLux admin app**, which signs you
in with your staff email and password. Superusers can also open the built-in
**Django admin** at `/django-admin/`, which offers the same order and catalogue
actions and is the only place to create staff accounts. Nothing here needs a
developer.

Payment is **cash on delivery only**. There is no online payment to reconcile.

Two things in this shop **do not fix themselves, and nothing warns you when they go
wrong**. Each is recoverable in a few clicks, but only by someone who knows to look.
Read the first section before you open the shop, not after the first complaint.

---

## Before you open the shop

Do these once, in this order.

### 1. Fill in brands, categories, sizes and shades

A product needs a brand and a category, and each thing you sell needs a size.

- **Brands**: every brand you stock, with its logo. A brand you switch off
  (**inactive**) disappears from the shop together with all its products, without
  deleting anything.
- **Categories**: for example Skincare, with Cleanse and Tone under it. Shoppers who
  pick Skincare also see everything in the categories under it.
- **Sizes**: every volume or weight you sell (`30 ml`, `100 g`), or `One size`.
  The *sort order* number decides the order they appear in; small numbers first.
- **Shades**: only for products that come in colours, such as foundations and
  lipsticks. Each shade has a swatch colour written as `#RRGGBB`. Skincare usually
  has no shade at all.
- **Skin types**: Normal, Dry, Oily and so on. Tick the ones each skincare or body
  product suits; shoppers can filter by them. A product can also carry a short
  *skin feel* ("Soothed, balanced, refreshed") and its *key ingredients*.

A size, shade, brand or category that is in use cannot be deleted. Rename it or
switch the brand off instead. Deleting a skin type is allowed: it is simply removed
from the products that had it.

### 2. Decide who gets a staff account

Anyone with a staff account can do **everything**: cancel orders, change stock and
prices, and read every customer's address and phone number. There are no limited
roles. Give staff accounts only to people you would trust with the whole shop.

Staff accounts are created by a superuser in the Django admin
(**Users → Add**, then tick **Staff status**).

---

## The two things you must check regularly

### Every day: confirm new orders, and cancel the ones you cannot confirm

**What happens.** When a customer places an order, the shop immediately sets their
items aside. That stops two people buying the last lipstick. But an order you never
confirm keeps those items aside forever. Nothing releases them.

**What to do.**

1. Open **Orders** and filter by status **Pending**.
2. Call each customer on the phone number on the order. When they confirm, move
   the order to **Confirmed**.
3. If you cannot reach them after a reasonable try, move the order to
   **Cancelled**. The items go straight back on sale.

### When a customer says they got no email: resend it

**What happens.** Each email is sent once. If it fails, **nothing tries again**,
and nothing tells you it failed. The confirmation email holds the customer's only
link back to their order: there are no customer accounts.

**What to do.** In the Django admin, open **Orders → Orders**, select the order and
run **Resend the confirmation email** or **Resend the shipping notice**. The email
always goes to the address on the order; correct the address first if it is wrong.

---

## Day-to-day

### Taking an order through to delivery

An order moves **Pending → Confirmed → Shipped → Delivered**. It can be
**Cancelled** while it is Pending or Confirmed. The admin app only offers the moves
that are allowed from where the order is.

| Move to | When |
| --- | --- |
| **Confirmed** | You spoke to the customer and they want the order |
| **Shipped** | Handed to the courier. **This emails the customer.** |
| **Delivered** | The courier confirmed delivery |
| **Cancelled** | The customer cancelled or could not be reached. Stock is returned |

Once an order has shipped it can no longer be cancelled.

### Recording the cash

When the courier hands over the cash, open **Payments** in the Django admin, select
that order's payment and run **Mark cash as collected**. This only records the cash;
it does not change the order.

### Adding a product

1. Create the product with its name, brand, category, price and description. It
   starts **unpublished**.
2. Add its variants: one per size and shade you sell (a serum in two sizes is two
   variants; a foundation in six shades is six). Each variant has its own code
   (SKU), stock count and, if it costs more than the product price, its own price.
3. Add photos and choose the main one.
4. **Publish** the product. The shop refuses to publish a product with no variants.

Stock is always the counted total on your shelf, not a change to the number.

### Product photos

Photos must be JPEG, PNG or WebP and no larger than 5 MB. Removing a photo removes
it from the shop, but **the file itself stays on the image service**.

---

## What the shop cannot do

- **Online payment.** Cash on delivery only.
- **Refunds, partial cancellation or editing an order.** Cancel and ask the
  customer to order again.
- **Customer accounts.** Customers reach their order only through the link in their
  email.
- **Anything scheduled.** Every check here happens because a person does it.

---

## When something is wrong and this document does not cover it

Write down the order number, what you expected and what you saw, and send it to
whoever maintains the shop.
