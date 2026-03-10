---
id: 456789ab-cdef-0123-4567-89abcdef0123
date: 2026-02-15T11:00:00
type: decision
scope: general
title: "Graceful Shutdown Ordering"
tags: ["graceful-shutdown", "lifecycle", "kubernetes", "deployment"]
related: ["[[20260210090000 Immutable Infrastructure Principle]]", "[[20260210140000 Blue-Green vs Canary Deployments]]"]
summary: "Decided on a specific shutdown ordering for services in Kubernetes: stop accepting, drain in-flight, close connections, flush metrics"
cb_source: hook-extraction
cb_created: 2026-02-15T11:00:00
---

## Graceful Shutdown Ordering

### Decision

Standardized shutdown sequence for all services:

1. **SIGTERM received** — stop accepting new requests (remove from load balancer)
2. **Drain period** (30s) — complete in-flight requests
3. **Close connections** — database pools, Redis, message consumers
4. **Flush** — metrics, logs, trace spans
5. **Exit 0**

### Kubernetes Configuration

```yaml
terminationGracePeriodSeconds: 45  # 30s drain + 15s buffer
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 5"]  # wait for endpoint removal
```

The 5-second preStop sleep is critical: Kubernetes endpoint removal is asynchronous. Without the sleep, the pod may receive traffic after it stops accepting connections.

### Rationale

We saw 502 errors during deployments because pods were killed before the load balancer stopped routing to them. The preStop sleep + terminationGracePeriodSeconds solved this.
