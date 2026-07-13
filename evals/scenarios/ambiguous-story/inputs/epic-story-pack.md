# Epic Story Pack — PROJ-100 Checkout Discounts

## Epic PROJ-100: Order discount support

Business goal: let customers apply discount codes at checkout to increase
conversion. Discounts must never reduce an order total below zero.

## Story PROJ-101: Apply discount code at checkout (target story)

As a customer I want to enter a discount code at checkout so that the order
total is reduced.

Description:
- Discount code field appears below the cart summary, right-aligned, with
  placeholder text "Enter code", max width 240px, error text in red below the
  field, and a "Apply" button disabled until 3+ characters are entered.
- Valid codes reduce the order total immediately without page reload.
- The discount service is called to validate the code.

Acceptance criteria:
1. Given a valid code, when the customer applies it, the total is updated.
2. The discount experience should feel fast and smooth.
3. Codes are case-insensitive.

## Story PROJ-102: Discount cap for large orders (sibling)

As a finance owner I want discounts capped at 15% of the order total so that
margin is protected.

Acceptance criteria:
1. Any discount exceeding 15% of the order subtotal is reduced to 15%.

## Story PROJ-103: Seasonal promotion codes (sibling)

As a marketing manager I want seasonal codes granting a flat 20% off so that
campaigns are simple to communicate.

Acceptance criteria:
1. Seasonal codes always apply exactly 20% off the subtotal.
