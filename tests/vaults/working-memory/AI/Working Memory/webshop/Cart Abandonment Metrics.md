---
id: wm-a2222222-2222-2222-2222-222222222222
date: 2026-02-05T14:00:00
type: reference
scope: project
title: "Cart Abandonment Metrics"
project: webshop
tags: ["metrics", "cart", "analytics", "webshop"]
related: []
summary: "Current cart abandonment rate is 73%; tracking events added to identify drop-off points in the checkout flow"
cb_source: hook-extraction
cb_created: 2026-02-05T14:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_PAST_2
---

## Cart Abandonment Metrics

### Current Numbers

- Cart abandonment rate: 73% (industry average: 70%)
- Top drop-off points:
  1. Shipping cost reveal: 35% abandon
  2. Account creation required: 22% abandon
  3. Payment form: 16% abandon

### Tracking Events Added

- `cart_checkout_started` — entered checkout flow
- `cart_shipping_calculated` — shipping cost displayed
- `cart_account_prompt` — account creation screen shown
- `cart_payment_started` — payment form rendered
- `cart_payment_submitted` — payment form submitted
- `cart_completed` — order confirmed

### Next Steps

- Implement guest checkout to eliminate account creation drop-off
- Show estimated shipping earlier (product page or cart summary)
- A/B test shipping cost thresholds for free shipping offers
