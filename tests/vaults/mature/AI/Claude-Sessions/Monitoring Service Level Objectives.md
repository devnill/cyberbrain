---
id: aa161616-1616-1616-1616-161616161616
date: 2026-02-15T10:00:00
type: decision
scope: general
title: "Monitoring Service Level Objectives"
project: general
tags: ["slo", "monitoring", "sre", "reliability"]
related: ["[[Observability is Not Just Logging]]"]
summary: "Defined SLOs for API availability (99.9%) and latency (P99 under 500ms) as the primary reliability targets"
cb_source: hook-extraction
cb_created: 2026-02-15T10:00:00
---

## Monitoring Service Level Objectives

### Defined SLOs

| Service | SLI | SLO | Error Budget (monthly) |
|---------|-----|-----|----------------------|
| API Gateway | Availability (non-5xx) | 99.9% | 43.2 minutes |
| API Gateway | Latency P99 | < 500ms | N/A |
| Auth Service | Availability | 99.95% | 21.6 minutes |
| Background Jobs | Completion within SLA | 95% | 36 hours |

### Error Budget Policy

- Above 50% remaining: deploy freely
- 25-50% remaining: require additional review for risky changes
- Below 25%: freeze non-critical deployments, focus on reliability
- Exhausted: incident review required before resuming deployments
