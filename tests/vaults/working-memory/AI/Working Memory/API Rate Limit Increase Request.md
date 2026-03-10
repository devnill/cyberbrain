---
id: wm-b4444444-4444-4444-4444-444444444444
date: 2026-02-27T11:00:00
type: problem
scope: general
title: "API Rate Limit Increase Request"
tags: ["api", "rate-limiting", "vendor", "pending"]
related: []
summary: "Third-party geocoding API rate limit of 100 req/s is insufficient for bulk address validation; increase request submitted"
cb_source: hook-extraction
cb_created: 2026-02-27T11:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_4
---

## API Rate Limit Increase Request

### Context

The geocoding API (MapBox) has a rate limit of 100 requests/second on our current plan. Bulk address validation during data imports can generate 500+ req/s.

### Current Workaround

- Queue-based throttling with 100ms delay between batches
- Import that takes 10 minutes would take 50 minutes with throttling

### Request Status

- Submitted rate limit increase request to MapBox support on 2026-02-27
- Requested: 1000 req/s (enterprise tier)
- Expected response: 3-5 business days
- Fallback: switch to Google Geocoding API if denied
