---
id: aa444444-4444-4444-4444-444444444444
date: 2026-01-18T10:30:00
type: insight
scope: general
title: "Observability is Not Just Logging"
project: general
tags: ["observability", "monitoring", "tracing", "metrics"]
related: []
summary: "The three pillars of observability serve different diagnostic needs: logs for what happened, metrics for how much, traces for where"
cb_source: hook-extraction
cb_created: 2026-01-18T10:30:00
---

## Observability is Not Just Logging

### The Three Pillars

1. **Logs** — discrete events, answer "what happened?"
2. **Metrics** — aggregated measurements, answer "how much?"
3. **Traces** — request-scoped execution paths, answer "where in the system?"

### When Each Matters

- **Debugging a specific failure**: logs (find the error, read the context)
- **Detecting anomalies**: metrics (is error rate above normal?)
- **Finding bottlenecks**: traces (which service is slow? which dependency?)

### The Missing Piece

None of these tell you *why* something happened. Correlation across all three is what gives you the full picture. A metric spike triggers investigation → traces narrow to a service → logs in that service reveal the root cause.

The investment in observability tooling that correlates across pillars (e.g., Grafana linking metrics → traces → logs) pays for itself in incident response time.
