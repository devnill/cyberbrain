---
id: a1234567-bcde-f012-3456-789abcdef012
date: 2026-02-07T10:00:00
type: reference
scope: general
title: "Idempotency Keys for API Retries"
tags: ["idempotency", "api-design", "reliability", "distributed-systems"]
related: ["[[20260205143000 Compensating Transactions Design]]", "[[20260205110000 Saga Pattern for Distributed Transactions]]"]
summary: "Idempotency key implementation for safe API retries using a server-side response cache keyed by client-provided idempotency key"
cb_source: hook-extraction
cb_created: 2026-02-07T10:00:00
---

## Idempotency Keys for API Retries

### Pattern

1. Client generates a unique key (UUID v4) and sends it in `Idempotency-Key` header
2. Server checks if the key exists in the idempotency store
3. If exists: return the cached response (same status code, same body)
4. If not: process the request, cache the response keyed by the idempotency key

### Storage

- Redis with TTL (24-48 hours) for the response cache
- Store: `{key: idempotency_key, status: int, body: bytes, created_at: timestamp}`
- TTL prevents unbounded growth

### Edge Cases

- Client retries before the first request completes: use a lock (Redis `SET NX`) to serialize
- Response is an error: cache it anyway (the client should generate a new key to retry)
- Key reuse with different request body: return 422 (prevent accidental misuse)
