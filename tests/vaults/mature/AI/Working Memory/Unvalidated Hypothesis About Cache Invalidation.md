---
id: dd444444-4444-4444-4444-444444444444
date: 2026-03-01T10:00:00
type: insight
scope: general
title: "Unvalidated Hypothesis About Cache Invalidation"
tags: ["caching", "hypothesis", "performance"]
related: []
summary: "Hypothesis that cache invalidation delays in the CDN layer cause the stale data reports; needs A/B test to confirm"
cb_source: hook-extraction
cb_created: 2026-03-01T10:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_2
---

## Unvalidated Hypothesis About Cache Invalidation

Users are reporting stale data on the dashboard after updates. Hypothesis: the CDN cache TTL (5 minutes) is too long for frequently changing data.

### Evidence For

- Reports cluster around cache TTL boundaries
- Direct API calls return correct data

### Evidence Against

- Some reports occur within seconds of an update (faster than any cache delay)
- CDN cache-hit headers show low hit rates for dashboard endpoints

### Next Steps

- Instrument cache hit/miss rates per endpoint
- Run A/B test with reduced TTL (30s) on a subset of users
- If confirmed, implement cache purge on write for affected endpoints
