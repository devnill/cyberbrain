---
id: a1b2c3d4-5e6f-7a8b-9c0d-e1f2a3b4c5d6
date: 2026-02-15T10:30:00
type: decision
scope: project
title: "Rate Limiting Strategy"
project: api-gateway
tags: ["rate-limiting", "api-gateway", "redis", "throttling"]
related: ["[[Token Bucket vs Sliding Window]]"]
summary: "Chose token bucket algorithm with Redis backend for API rate limiting over sliding window approach"
cb_source: hook-extraction
cb_created: 2026-02-15T10:30:00
---

## Rate Limiting Strategy

After evaluating both token bucket and sliding window approaches for the API gateway rate limiter, we chose token bucket with a Redis backend.

### Alternatives Considered

1. **Sliding window counter** — simpler to implement, but doesn't handle burst traffic well. The fixed window boundary causes spike allowance at window edges.
2. **Token bucket** — allows controlled bursts while maintaining average rate. More complex but better UX for API consumers.
3. **Leaky bucket** — smooth output rate but penalizes legitimate burst patterns too aggressively.

### Decision

Token bucket with Redis `MULTI/EXEC` for atomic token consumption. Each API key gets a bucket with configurable capacity and refill rate. Redis TTL handles bucket expiration for inactive keys.

### Rationale

- API consumers expect burst tolerance (webhook retries, batch operations)
- Redis gives us distributed state across gateway instances
- Token bucket math is well-understood and easy to tune per tier

