---
id: 23456789-abcd-ef01-2345-6789abcdef01
date: 2026-02-13T10:00:00
type: insight
scope: general
title: "Feature Flags as Technical Debt"
tags: ["feature-flags", "technical-debt", "code-quality"]
related: ["[[20260210140000 Blue-Green vs Canary Deployments]]"]
summary: "Feature flags that outlive their rollout purpose become hidden complexity — every flag doubles the state space the code must handle"
cb_source: hook-extraction
cb_created: 2026-02-13T10:00:00
---

## Feature Flags as Technical Debt

Feature flags are essential for safe rollouts but become technical debt the moment the rollout is complete. Each flag doubles the number of code paths that must be tested and maintained.

### Flag Lifecycle

1. **Create** — for a specific rollout purpose
2. **Ramp** — gradual traffic increase
3. **Ship** — 100% traffic, flag is redundant
4. **Remove** — clean up the flag and dead code path

Step 4 almost never happens. The result: code full of `if flag_enabled("old_feature")` branches where `old_feature` has been at 100% for 18 months.

### Prevention

- Every flag has an expiration date in the flag management system
- Expired flags trigger a Jira ticket for removal
- Track flag count as a code health metric
- Maximum flag lifetime: 90 days (with exception process)
