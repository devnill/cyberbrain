---
id: aa151515-1515-1515-1515-151515151515
date: 2026-01-08T09:00:00
type: reference
scope: general
title: "Strangler Fig Pattern"
project: general
tags: ["strangler-fig", "migration", "legacy", "patterns"]
related: []
summary: "Incremental migration strategy where new functionality gradually replaces old, avoiding big-bang rewrites"
cb_source: hook-extraction
cb_created: 2026-01-08T09:00:00
---

## Strangler Fig Pattern

### How It Works

1. Place a facade (proxy/gateway) in front of the legacy system
2. New features are built in the new system behind the facade
3. Existing features are gradually migrated from old to new
4. The facade routes requests to old or new based on the migration state
5. When migration is complete, remove the old system

### Key Principles

- The facade is transparent to clients (they don't know which system handles the request)
- Migration is incremental and reversible (roll back individual routes)
- Both systems can run simultaneously during the transition
- Each migration step is small enough to be low-risk

### Risks

- The facade adds latency and operational complexity
- Data synchronization between old and new during the transition
- The "last 20%" of migration is the hardest (edge cases, undocumented behavior)
