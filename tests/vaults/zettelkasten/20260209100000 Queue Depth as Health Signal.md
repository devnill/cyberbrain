---
id: c3456789-def0-1234-5678-9abcdef01234
date: 2026-02-09T10:00:00
type: insight
scope: general
title: "Queue Depth as Health Signal"
tags: ["queues", "monitoring", "observability", "sre"]
related: ["[[20260208140000 Backpressure Mechanisms]]"]
summary: "Queue depth trend (growing, stable, draining) is a better health signal than absolute depth because it reveals whether the system is keeping up"
cb_source: hook-extraction
cb_created: 2026-02-09T10:00:00
---

## Queue Depth as Health Signal

Alerting on absolute queue depth is fragile — the "right" depth depends on traffic patterns. A queue of 10,000 messages during a traffic spike is fine if it's draining. A queue of 100 messages that's growing is a problem.

### Better Signal: Depth Trend

- **Growing**: consumer is slower than producer → investigate consumer
- **Stable**: producer and consumer are matched → healthy
- **Draining**: consumer is catching up → recovering

### Alert on Rate of Change

```promql
rate(queue_depth[5m]) > 100  # growing by 100 msgs/min for 5 minutes
```

This catches the problem regardless of absolute depth and avoids false alarms during normal spikes.
