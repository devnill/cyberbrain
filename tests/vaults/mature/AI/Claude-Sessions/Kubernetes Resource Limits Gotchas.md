---
id: aa555555-5555-5555-5555-555555555555
date: 2026-01-20T11:00:00
type: reference
scope: general
title: "Kubernetes Resource Limits Gotchas"
project: general
tags: ["kubernetes", "resources", "cpu", "memory", "performance"]
related: []
summary: "Common mistakes with Kubernetes resource limits including CPU throttling, OOM behavior, and the difference between requests and limits"
cb_source: hook-extraction
cb_created: 2026-01-20T11:00:00
---

## Kubernetes Resource Limits Gotchas

### CPU Throttling

- CPU limits use CFS (Completely Fair Scheduler) with 100ms periods
- A pod with 500m CPU limit gets 50ms of CPU per 100ms period
- Burst workloads (handle request in 20ms, then idle) get throttled even at low average utilization
- Solution: set requests (for scheduling) but consider removing CPU limits (controversial but effective)

### Memory

- Memory limits are hard: exceed them and the pod is OOM-killed
- Memory requests affect scheduling (which node has room)
- Set requests = limits for memory (avoid overcommit and unpredictable OOM kills)

### Common Mistakes

1. Setting limits too low → CPU throttling looks like application slowness
2. Setting requests too high → cluster underutilization, scheduling failures
3. Not setting requests at all → best-effort QoS class, first to be evicted
4. Using `resources.limits.memory` much higher than `resources.requests.memory` → overcommit, random OOM kills under pressure
