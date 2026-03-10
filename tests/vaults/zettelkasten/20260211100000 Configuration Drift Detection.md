---
id: f6789012-0123-4567-89ab-cdef01234567
date: 2026-02-11T10:00:00
type: problem
scope: general
title: "Configuration Drift Detection"
tags: ["configuration-drift", "devops", "compliance", "terraform"]
related: ["[[20260210090000 Immutable Infrastructure Principle]]"]
summary: "Manual infrastructure changes caused configuration drift that made Terraform plans unreliable; resolved with drift detection pipeline"
cb_source: hook-extraction
cb_created: 2026-02-11T10:00:00
---

## Configuration Drift Detection

### Problem

Engineers were making manual changes via AWS console during incidents. These changes weren't reflected in Terraform state, causing subsequent `terraform plan` to show unexpected diffs or, worse, revert the manual fixes.

### Solution

1. Scheduled `terraform plan` (no apply) runs every 6 hours via CI
2. Any diff triggers a Slack notification to the infrastructure channel
3. The notification includes the drift summary and a link to the plan output
4. SLA: all drift must be reconciled (codified or reverted) within 24 hours

### Prevention

- Read-only AWS console access by default (break-glass for incidents)
- Post-incident checklist includes "codify any manual infrastructure changes"
- Terraform state is the source of truth, not the cloud provider console
