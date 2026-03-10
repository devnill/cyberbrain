---
id: dd333333-3333-3333-3333-333333333333
date: 2026-02-25T11:00:00
type: problem
scope: project
title: "Temporary Workaround for Rate Limiter"
project: myproject
tags: ["rate-limiting", "workaround", "technical-debt"]
related: []
summary: "Bypassed rate limiter for internal service calls by IP allowlisting; needs proper solution with service-to-service auth"
cb_source: hook-extraction
cb_created: 2026-02-25T11:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_1
---

## Temporary Workaround for Rate Limiter

Internal service calls were getting rate-limited because they come from the same IP range as external traffic. Quick fix: added internal IP ranges to the rate limiter allowlist.

### Why This Is Temporary

- IP-based allowlisting is fragile (IPs change, new services added)
- Proper solution: mTLS or API key-based service identity
- Rate limiting should be per-identity, not per-IP

### TODO

- Design service-to-service authentication
- Implement rate limiting by service identity
- Remove IP allowlist
