---
id: e5678901-f012-3456-789a-bcdef0123456
date: 2026-02-10T14:00:00
type: reference
scope: general
title: "Blue-Green vs Canary Deployments"
tags: ["deployment", "blue-green", "canary", "devops"]
related: ["[[20260210090000 Immutable Infrastructure Principle]]"]
summary: "Comparison of blue-green and canary deployment strategies with decision criteria for choosing between them"
cb_source: hook-extraction
cb_created: 2026-02-10T14:00:00
---

## Blue-Green vs Canary Deployments

### Blue-Green

- Two identical environments (blue = current, green = new)
- Deploy to green, test, switch traffic
- Rollback: switch traffic back to blue
- Pro: instant rollback, full testing before exposure
- Con: 2x infrastructure cost, database schema changes are tricky

### Canary

- Deploy new version to a small subset (e.g., 5% of traffic)
- Monitor error rates and latency
- Gradually increase traffic percentage
- Rollback: route all traffic to old version
- Pro: catches issues with real traffic, lower infrastructure cost
- Con: slower rollout, need good observability

### Decision Criteria

- Use blue-green when: database migrations are simple, full pre-production testing is needed, cost is not a constraint
- Use canary when: changes are risky, you need real traffic validation, gradual rollout matters
