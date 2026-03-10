---
id: aa121212-1212-1212-1212-121212121212
date: 2026-01-12T09:00:00
type: reference
scope: general
title: "Twelve-Factor App Checklist"
project: general
tags: ["twelve-factor", "cloud-native", "architecture", "checklist"]
related: []
summary: "Condensed twelve-factor app checklist with compliance status for our services"
cb_source: hook-extraction
cb_created: 2026-01-12T09:00:00
---

## Twelve-Factor App Checklist

| Factor | Status | Notes |
|--------|--------|-------|
| 1. Codebase | Done | One repo per service |
| 2. Dependencies | Done | requirements.txt / poetry.lock |
| 3. Config | Done | Environment variables |
| 4. Backing services | Done | Configured via URLs |
| 5. Build, release, run | Done | CI/CD pipeline |
| 6. Processes | Done | Stateless, shared-nothing |
| 7. Port binding | Done | Self-contained HTTP servers |
| 8. Concurrency | Partial | Horizontal scaling, but some batch jobs are single-process |
| 9. Disposability | Done | Fast startup, graceful shutdown |
| 10. Dev/prod parity | Partial | Docker Compose locally, Kubernetes in prod |
| 11. Logs | Done | Stdout, collected by Datadog |
| 12. Admin processes | Partial | Migrations automated, some manual scripts remain |
