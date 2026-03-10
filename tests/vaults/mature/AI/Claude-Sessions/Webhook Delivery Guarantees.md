---
id: aabbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
date: 2026-02-03T15:00:00
type: reference
scope: general
title: "Webhook Delivery Guarantees"
project: general
tags: ["webhooks", "delivery", "reliability", "api-design"]
related: []
summary: "Implementing at-least-once webhook delivery with exponential backoff, idempotency keys, and a dead letter queue for failed deliveries"
cb_source: hook-extraction
cb_created: 2026-02-03T15:00:00
---

## Webhook Delivery Guarantees

### At-Least-Once Delivery

1. Persist webhook event to database before sending
2. Send HTTP POST to subscriber URL
3. If 2xx response: mark as delivered
4. If non-2xx or timeout: schedule retry with exponential backoff

### Retry Schedule

- Attempt 1: immediate
- Attempt 2: 1 minute
- Attempt 3: 5 minutes
- Attempt 4: 30 minutes
- Attempt 5: 2 hours
- Attempt 6: 12 hours
- After 6 failures: move to dead letter queue, notify subscriber

### Subscriber Contract

- Must respond with 2xx within 30 seconds
- Must handle duplicate deliveries (use the event ID for idempotency)
- Must verify webhook signature (HMAC-SHA256 of the payload)
