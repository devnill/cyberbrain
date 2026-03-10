---
id: d0e1f2a3-4b5c-6d7e-8f9a-b0c1d2e3f4a5
date: 2026-02-25T11:15:00
type: reference
scope: general
title: "Prometheus Alerting Thresholds"
project: devops
tags: ["prometheus", "alerting", "monitoring", "sre"]
related: []
summary: "Current alerting thresholds for production services with rationale for each threshold value"
cb_source: hook-extraction
cb_created: 2026-02-25T11:15:00
---

## Prometheus Alerting Thresholds

### API Services

| Metric | Warning | Critical | Window | Rationale |
|--------|---------|----------|--------|-----------|
| Error rate (5xx) | 1% | 5% | 5 min | Below 1% is normal noise from client disconnects |
| P99 latency | 2s | 5s | 5 min | SLA target is P99 < 3s |
| Request rate drop | 30% | 50% | 10 min | Detects routing failures |
| Memory usage | 80% | 90% | 5 min | OOM kill at 100% |
| CPU usage | 70% | 85% | 10 min | Autoscaling triggers at 75% |

### Database

| Metric | Warning | Critical | Window |
|--------|---------|----------|--------|
| Connection pool usage | 70% | 90% | 5 min |
| Replication lag | 5s | 30s | 1 min |
| Slow queries/min | 10 | 50 | 5 min |

### Alert Routing

- Critical: PagerDuty + Slack #incidents
- Warning: Slack #alerts only
- Use `for: <window>` in Prometheus rules to avoid flapping
