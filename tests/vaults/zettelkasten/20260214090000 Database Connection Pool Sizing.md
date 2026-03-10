---
id: 3456789a-bcde-f012-3456-789abcdef012
date: 2026-02-14T09:00:00
type: reference
scope: general
title: "Database Connection Pool Sizing"
tags: ["database", "connection-pool", "performance", "postgresql"]
related: ["[[20260208140000 Backpressure Mechanisms]]"]
summary: "Connection pool sizing formula and gotchas including the HikariCP recommendation of pool size equals CPU cores times 2 plus disk spindles"
cb_source: hook-extraction
cb_created: 2026-02-14T09:00:00
---

## Database Connection Pool Sizing

### HikariCP Formula

```
pool_size = (core_count * 2) + effective_spindle_count
```

For SSD-backed databases, effective spindle count is effectively 0-1:

- 4-core server → pool size 9-10
- 8-core server → pool size 17-18

### Common Mistakes

1. **Too large**: 100+ connections per instance × 20 instances = 2000 connections hitting PostgreSQL. `max_connections` defaults to 100.
2. **Too small**: application threads block waiting for connections, latency spikes
3. **Not accounting for replicas**: read replicas need their own pools, sized independently

### Guidelines

- Start small (10-20), measure, adjust
- Monitor pool wait time (>10ms = too small)
- Monitor active connections vs pool size (>80% sustained = too small)
- Use PgBouncer for connection multiplexing if instance count × pool size > database max_connections
