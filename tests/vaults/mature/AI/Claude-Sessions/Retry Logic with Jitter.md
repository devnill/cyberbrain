---
id: aa191919-1919-1919-1919-191919191919
date: 2026-01-16T10:00:00
type: reference
scope: general
title: "Retry Logic with Jitter"
project: general
tags: ["retry", "jitter", "resilience", "distributed-systems"]
related: []
summary: "Exponential backoff with full jitter prevents thundering herd on service recovery"
cb_source: hook-extraction
cb_created: 2026-01-16T10:00:00
---

## Retry Logic with Jitter

### The Problem with Plain Exponential Backoff

If 1000 clients fail simultaneously and retry with the same backoff schedule, they all retry at the same times — creating periodic load spikes.

### Solution: Full Jitter

```python
import random

def retry_delay(attempt, base_delay=1.0, max_delay=60.0):
    exp_delay = min(base_delay * (2 ** attempt), max_delay)
    return random.uniform(0, exp_delay)
```

Full jitter randomizes the delay from 0 to the exponential ceiling. This spreads retries uniformly across the delay window.

### Comparison

| Strategy | Retries at t=4s (1000 clients) |
|----------|-------------------------------|
| No backoff | 1000 |
| Exponential backoff | 1000 |
| Exp backoff + full jitter | ~125 |
