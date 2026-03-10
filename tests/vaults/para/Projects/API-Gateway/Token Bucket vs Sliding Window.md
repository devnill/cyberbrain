---
id: b2c3d4e5-6f7a-8b9c-0d1e-f2a3b4c5d6e7
date: 2026-02-14T14:15:00
type: reference
scope: project
title: "Token Bucket vs Sliding Window"
project: api-gateway
tags: ["rate-limiting", "algorithms", "api-gateway"]
related: ["[[Rate Limiting Strategy]]"]
summary: "Comparison of token bucket and sliding window rate limiting algorithms with implementation trade-offs"
cb_source: hook-extraction
cb_created: 2026-02-14T14:15:00
---

## Token Bucket vs Sliding Window

### Token Bucket

- Tokens added at fixed rate, consumed per request
- Allows bursts up to bucket capacity
- Redis: `MULTI` with `GET`, `SET`, `EXPIRE`
- Memory: O(1) per key

### Sliding Window

- Count requests in trailing time window
- Two variants: fixed window counters, sliding log
- Fixed window: simple but boundary spike problem
- Sliding log: accurate but O(n) memory per key

### Performance Comparison

| Metric | Token Bucket | Sliding Window (fixed) | Sliding Window (log) |
|--------|-------------|----------------------|---------------------|
| Memory per key | 16 bytes | 8 bytes | ~100 bytes/req |
| Redis ops/check | 3 (MULTI) | 2 (INCR+EXPIRE) | 3+ (ZRANGEBYSCORE) |
| Burst handling | Controlled | Edge spikes | Accurate |
| Implementation | Medium | Simple | Complex |
