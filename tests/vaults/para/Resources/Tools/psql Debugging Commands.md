---
id: d6e7f8a9-0b1c-2d3e-4f5a-b6c7d8e9f0a1
date: 2026-01-20T14:30:00
type: reference
scope: general
title: "psql Debugging Commands"
project: tools
tags: ["postgresql", "debugging", "database", "cli"]
related: []
summary: "Useful psql commands for debugging production database issues including locks, slow queries, and connection analysis"
cb_source: hook-extraction
cb_created: 2026-01-20T14:30:00
---

## psql Debugging Commands

### Active Queries

```sql
SELECT pid, now() - pg_stat_activity.query_start AS duration,
       query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;
```

### Blocking Locks

```sql
SELECT blocked.pid AS blocked_pid,
       blocked.query AS blocked_query,
       blocking.pid AS blocking_pid,
       blocking.query AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_locks bl ON bl.pid = blocked.pid
JOIN pg_locks kl ON kl.locktype = bl.locktype
  AND kl.relation = bl.relation
  AND kl.pid != bl.pid
JOIN pg_stat_activity blocking ON kl.pid = blocking.pid
WHERE NOT bl.granted;
```

### Table Sizes

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;
```

### Connection Count

```sql
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;
```
