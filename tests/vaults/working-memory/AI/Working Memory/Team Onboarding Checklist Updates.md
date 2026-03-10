---
id: wm-c5555555-5555-5555-5555-555555555555
date: 2026-03-06T11:00:00
type: reference
scope: general
title: "Team Onboarding Checklist Updates"
tags: ["onboarding", "documentation", "team", "process"]
related: []
summary: "Onboarding checklist needs updates for new CI/CD pipeline, Kubernetes access, and monitoring dashboards"
cb_source: hook-extraction
cb_created: 2026-03-06T11:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_FUTURE_5
---

## Team Onboarding Checklist Updates

### Items to Add

- [ ] Request Kubernetes cluster access via IT portal
- [ ] Set up kubectl with kubeconfig from 1Password vault
- [ ] Import Grafana dashboards (team-services, team-infrastructure)
- [ ] Join Slack channels: #incidents, #deployments, #data-pipeline-alerts
- [ ] Complete security training module (mandatory, deadline: day 5)
- [ ] Set up local development environment with Tilt (replaces Docker Compose)

### Items to Remove

- Docker Compose setup instructions (deprecated)
- Jenkins pipeline documentation (replaced by GitHub Actions)
- VPN setup (replaced by Tailscale mesh)

### Items to Update

- Git workflow section (rebase-before-merge, not merge commits)
- Code review guidelines (link to updated PR template)
