---
id: a3b4c5d6-7e8f-9a0b-1c2d-e3f4a5b6c7d8
date: 2026-01-28T16:30:00
type: reference
scope: general
title: "Circuit Breaker Pattern"
project: patterns
tags: ["circuit-breaker", "resilience", "distributed-systems", "patterns"]
related: ["[[Gateway Timeout Cascading]]"]
summary: "Circuit breaker implementation pattern with state machine transitions and configuration guidelines"
cb_source: hook-extraction
cb_created: 2026-01-28T16:30:00
---

## Circuit Breaker Pattern

### States

1. **Closed** (normal) — requests pass through, failures counted
2. **Open** — requests fail immediately, no downstream calls
3. **Half-Open** — limited requests pass through to test recovery

### State Transitions

```
Closed --[failure threshold exceeded]--> Open
Open --[timeout elapsed]--> Half-Open
Half-Open --[probe succeeds]--> Closed
Half-Open --[probe fails]--> Open
```

### Configuration Guidelines

| Parameter | Recommended | Notes |
|-----------|------------|-------|
| Failure threshold | 5 failures in 10s | Avoid single-failure trips |
| Open duration | 30s | Enough for downstream recovery |
| Half-open probes | 3 requests | Statistical significance |
| Success threshold | 2/3 probes | Conservative re-close |

### Implementation Notes

- Per-service instances, not global
- Track failure rate, not just count (low-traffic services need rate-based)
- Log state transitions for incident analysis
- Expose circuit state via health endpoint for dashboard visibility
