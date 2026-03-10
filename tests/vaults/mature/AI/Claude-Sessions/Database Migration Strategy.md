---
id: aa181818-1818-1818-1818-181818181818
date: 2026-02-20T14:00:00
type: decision
scope: general
title: "Database Migration Strategy"
project: general
tags: ["database", "migration", "alembic", "deployment"]
related: ["[[API Versioning Strategies]]"]
summary: "Decided on forward-only migrations with backward-compatible schema changes to enable zero-downtime deployments"
cb_source: hook-extraction
cb_created: 2026-02-20T14:00:00
---

## Database Migration Strategy

### Decision

Forward-only migrations (no down migrations) with backward-compatible schema changes.

### Rules

1. **Add columns as nullable** or with defaults — never add NOT NULL without a default
2. **Never drop columns** in the same release — deprecate, then remove in a later release
3. **Never rename columns** — add new, migrate data, deprecate old, remove old
4. **Index creation uses CONCURRENTLY** — avoid locking production tables
5. **Large data migrations run as background jobs** — not in the migration script

### Rationale

Zero-downtime deployments require that the old code and new code can both run against the same database schema during the rollout window. Backward-compatible changes ensure this.

### Implementation

- Alembic for migration management
- Migrations run automatically in the CI/CD pipeline before deployment
- Manual review required for any migration touching >1M rows
