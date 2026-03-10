---
id: 5e6f7890-abcd-ef12-3456-789012345678
date: 2026-02-04T10:00:00
type: reference
scope: general
title: "Event Store Schema Design"
tags: ["event-sourcing", "schema", "database", "postgresql"]
related: ["[[20260203140000 CQRS Event Sourcing Synergy]]", "[[20260206090000 Schema Evolution with Upcasters]]"]
summary: "PostgreSQL-based event store schema with stream partitioning and optimistic concurrency"
cb_source: hook-extraction
cb_created: 2026-02-04T10:00:00
---

## Event Store Schema Design

```sql
CREATE TABLE events (
    id          BIGSERIAL PRIMARY KEY,
    stream_id   TEXT NOT NULL,
    version     INT NOT NULL,
    event_type  TEXT NOT NULL,
    data        JSONB NOT NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (stream_id, version)
);

CREATE INDEX idx_events_stream ON events (stream_id, version);
CREATE INDEX idx_events_type ON events (event_type);
```

- `stream_id` groups events by aggregate (e.g., `order-123`)
- `version` enables optimistic concurrency (append only if expected version matches)
- `JSONB` for event data allows schema flexibility while keeping queryability
- The `UNIQUE (stream_id, version)` constraint prevents concurrent appends to the same stream
