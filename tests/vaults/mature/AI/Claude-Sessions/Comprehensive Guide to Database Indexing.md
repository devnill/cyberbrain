---
id: aacccccc-cccc-cccc-cccc-cccccccccccc
date: 2026-01-30T09:00:00
type: reference
scope: general
title: "Comprehensive Guide to Database Indexing"
project: general
tags: ["database", "indexing", "postgresql", "performance", "sql"]
related: ["[[Cursor Pagination for Large Datasets]]", "[[GraphQL N+1 Query Problem]]"]
summary: "Complete reference for database indexing strategies including B-tree, hash, GIN, GiST, BRIN, partial indexes, and expression indexes with PostgreSQL examples"
cb_source: hook-extraction
cb_created: 2026-01-30T09:00:00
---

## Comprehensive Guide to Database Indexing

### 1. B-tree Indexes (Default)

B-tree is the default index type in PostgreSQL and covers most use cases. It supports equality and range queries on sortable data types.

#### When to Use

- Equality lookups: `WHERE status = 'active'`
- Range queries: `WHERE created_at > '2026-01-01'`
- Sorting: `ORDER BY created_at DESC`
- Prefix matching: `WHERE name LIKE 'John%'` (but not `'%John'`)

#### Characteristics

- Balanced tree structure with O(log n) lookup
- Each leaf node contains pointers to heap tuples
- Supports multi-column indexes (leftmost prefix rule applies)
- Can be used for `MIN()`, `MAX()`, `COUNT(*)` optimizations via index-only scans

#### Multi-column Index Ordering

A composite index `(a, b, c)` supports queries on:
- `a` alone
- `a, b` together
- `a, b, c` together
- But NOT `b` alone or `c` alone

Think of it like a phone book sorted by last name, then first name. You can find all "Smiths" but you can't efficiently find all "Johns" across all last names.

#### Example

```sql
-- Composite index for common query pattern
CREATE INDEX idx_orders_status_date ON orders (status, created_at DESC);

-- This query uses the index efficiently
SELECT * FROM orders WHERE status = 'pending' ORDER BY created_at DESC LIMIT 20;

-- This query only uses the first column
SELECT * FROM orders WHERE status = 'shipped';

-- This query CANNOT use the index (missing leading column)
SELECT * FROM orders WHERE created_at > '2026-01-01';
```

### 2. Hash Indexes

Hash indexes support only equality comparisons. They were unreliable before PostgreSQL 10 (not WAL-logged) but are now safe.

#### When to Use

- Pure equality lookups on large values (UUIDs, long strings)
- When you never need range queries on the column

#### Characteristics

- O(1) average lookup (faster than B-tree for equality)
- Smaller than B-tree for the same data
- No support for range queries, sorting, or multi-column

#### Example

```sql
CREATE INDEX idx_sessions_token ON sessions USING hash (session_token);
```

### 3. GIN Indexes (Generalized Inverted Index)

GIN indexes are designed for composite values — arrays, JSONB, full-text search vectors.

#### When to Use

- JSONB containment queries: `WHERE data @> '{"status": "active"}'`
- Array operations: `WHERE tags @> ARRAY['urgent']`
- Full-text search: `WHERE to_tsvector('english', body) @@ to_tsquery('database & index')`

#### Characteristics

- Inverted index: maps each element to the rows containing it
- Slow to build and update (use `gin_pending_list_limit` for batched inserts)
- Fast for lookups, especially with many distinct values
- Supports `jsonb_path_ops` operator class for JSONB (smaller, faster for `@>` only)

#### Example

```sql
-- JSONB containment with optimized operator class
CREATE INDEX idx_events_data ON events USING gin (data jsonb_path_ops);

-- Full-text search
CREATE INDEX idx_articles_search ON articles USING gin (to_tsvector('english', title || ' ' || body));
```

### 4. GiST Indexes (Generalized Search Tree)

GiST is a framework for building balanced tree indexes for non-standard data types.

#### When to Use

- Geometric queries: `WHERE location <@ circle('(0,0)', 10)`
- Range type queries: `WHERE valid_during && tsrange('2026-01-01', '2026-12-31')`
- Exclusion constraints: `EXCLUDE USING gist (room WITH =, during WITH &&)`
- Nearest-neighbor search: `ORDER BY location <-> point(x, y) LIMIT 10`

#### Characteristics

- Lossy: may produce false positives that require a recheck against the heap
- Supports KNN (K-nearest-neighbor) via `<->` operator
- Used by PostGIS for spatial queries

#### Example

```sql
-- PostGIS spatial index
CREATE INDEX idx_locations_geom ON locations USING gist (geom);

-- Range exclusion constraint (no double-booking)
ALTER TABLE reservations ADD CONSTRAINT no_overlap
    EXCLUDE USING gist (room_id WITH =, time_range WITH &&);
```

### 5. BRIN Indexes (Block Range Index)

BRIN indexes store summary information about ranges of physical table blocks. Extremely small and effective for naturally ordered data.

#### When to Use

- Time-series data where rows are inserted in chronological order
- Large tables (millions of rows) where a B-tree would be too large
- Columns with strong correlation between value and physical position

#### Characteristics

- Much smaller than B-tree (often 1000x)
- Effective only when data is physically ordered by the indexed column
- Lossy: scans entire blocks, not individual rows
- Specify `pages_per_range` to tune granularity (default 128)

#### Example

```sql
-- Ideal for time-series: rows are inserted in order
CREATE INDEX idx_metrics_time ON metrics USING brin (recorded_at);

-- Check physical correlation (> 0.9 means BRIN is effective)
SELECT correlation FROM pg_stats WHERE tablename = 'metrics' AND attname = 'recorded_at';
```

### 6. Partial Indexes

Partial indexes cover a subset of rows, reducing index size and maintenance cost.

#### When to Use

- Queries that always filter on a specific condition
- Tables where most rows are in a "terminal" state (completed, archived) and queries target the "active" subset

#### Example

```sql
-- Only index active orders (5% of table)
CREATE INDEX idx_orders_active ON orders (created_at)
    WHERE status IN ('pending', 'processing');

-- Only this query benefits
SELECT * FROM orders WHERE status IN ('pending', 'processing') ORDER BY created_at;
```

### 7. Expression Indexes

Index on a computed expression rather than a raw column value.

#### When to Use

- Queries that apply functions to columns: `WHERE lower(email) = 'user@example.com'`
- Computed values used in WHERE or ORDER BY

#### Example

```sql
CREATE INDEX idx_users_email_lower ON users (lower(email));

-- This query uses the index
SELECT * FROM users WHERE lower(email) = 'user@example.com';

-- This query does NOT (different expression)
SELECT * FROM users WHERE email = 'user@example.com';
```

### 8. Covering Indexes (INCLUDE)

Include non-key columns in the index to enable index-only scans without adding them to the sort order.

#### When to Use

- Frequently queried column combinations where some columns are only in SELECT, not WHERE/ORDER BY

#### Example

```sql
-- Include name and email for index-only scan
CREATE INDEX idx_users_status ON users (status) INCLUDE (name, email);

-- Index-only scan: no heap access needed
SELECT name, email FROM users WHERE status = 'active';
```

### 9. Index Maintenance

#### Monitoring

```sql
-- Index usage statistics
SELECT relname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Unused indexes (candidates for removal)
SELECT relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND relname NOT LIKE 'pg_%';

-- Index sizes
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
```

#### Bloat

Indexes accumulate dead tuples from UPDATE/DELETE operations. REINDEX rebuilds them:

```sql
REINDEX INDEX CONCURRENTLY idx_orders_status_date;
```

Use `CONCURRENTLY` to avoid locking the table. Monitor bloat with `pgstattuple` extension.

#### Impact on Writes

Every index adds overhead to INSERT, UPDATE, DELETE operations. For write-heavy tables:

- Minimize index count
- Use partial indexes to reduce maintenance scope
- Consider batch index creation for bulk loads: drop indexes, load data, recreate indexes

### 10. Decision Framework

| Query Pattern | Index Type | Notes |
|--------------|-----------|-------|
| Equality + range | B-tree | Default choice |
| Equality only (large values) | Hash | Faster than B-tree for equality |
| JSONB queries | GIN | Use `jsonb_path_ops` for `@>` |
| Full-text search | GIN | On `tsvector` column |
| Geometric/spatial | GiST | PostGIS integration |
| Range overlaps | GiST | Exclusion constraints |
| Time-series (ordered) | BRIN | 1000x smaller than B-tree |
| Active subset | Partial | Reduce index size |
| Function in WHERE | Expression | Match the query expression exactly |
| Index-only scan | INCLUDE | Avoid heap access |

### 11. Concurrent Index Creation

Creating indexes on production tables can lock the table and block writes. PostgreSQL provides `CREATE INDEX CONCURRENTLY` to avoid this, but it comes with trade-offs.

#### How CONCURRENTLY Works

Instead of locking the table and scanning it once, `CONCURRENTLY` performs two passes:
1. First pass: scan the table and build the index without an exclusive lock
2. Wait for all transactions that started before the first pass to complete
3. Second pass: index any rows that were modified during the first pass

This means the index build takes longer (roughly 2-3x) but doesn't block reads or writes.

#### Limitations

- Cannot be used inside a transaction block
- If the build fails partway through, it leaves an `INVALID` index that must be dropped manually
- Requires additional disk space for the temporary build structures
- Cannot build unique indexes concurrently if there are existing duplicates

#### Example

```sql
-- Safe for production
CREATE INDEX CONCURRENTLY idx_orders_customer ON orders (customer_id);

-- Check for invalid indexes after a failed concurrent build
SELECT relname, indisvalid FROM pg_index JOIN pg_class ON pg_index.indexrelid = pg_class.oid
WHERE NOT indisvalid;

-- Drop and retry if invalid
DROP INDEX CONCURRENTLY idx_orders_customer;
CREATE INDEX CONCURRENTLY idx_orders_customer ON orders (customer_id);
```

### 12. Index-Only Scans Deep Dive

An index-only scan reads data directly from the index without accessing the table heap. This is the fastest possible query path but requires specific conditions.

#### Requirements

1. All columns in `SELECT`, `WHERE`, and `ORDER BY` must be in the index
2. The visibility map must show the pages as all-visible (recently vacuumed)
3. The query planner must estimate that an index-only scan is cheaper

#### Visibility Map

PostgreSQL tracks which table pages contain only tuples visible to all transactions. If a page has been modified since the last `VACUUM`, PostgreSQL must check the heap for that page even in an index-only scan.

```sql
-- Check visibility map coverage
SELECT relname,
       n_tup_ins + n_tup_upd + n_tup_del AS total_modifications,
       last_vacuum, last_autovacuum
FROM pg_stat_user_tables
WHERE relname = 'orders';
```

For tables with high write rates, frequent `VACUUM` is essential for index-only scan efficiency. Without it, you get "index-only scans" that still access the heap for most rows, negating the performance benefit.

#### Practical Impact

On a table with 10 million rows:
- Heap access for each row: ~0.1ms per random read
- Index-only scan: ~0.001ms per row (sequential within index)
- Difference for 1000-row result: 100ms vs 1ms

This makes covering indexes with `INCLUDE` extremely valuable for read-heavy workloads. The trade-off is increased index size and write overhead.

### 13. Multicolumn Index Column Ordering Strategy

The order of columns in a multicolumn index significantly affects which queries can use it efficiently. The optimal order depends on query patterns, not just which columns are filtered.

#### Equality Before Range

Place columns used in equality conditions before columns used in range conditions:

```sql
-- If queries are: WHERE status = 'active' AND created_at > '2026-01-01'
-- Good: equality column first
CREATE INDEX idx_eq_range ON orders (status, created_at);

-- Bad: range column first (index can't efficiently use status after range scan)
CREATE INDEX idx_range_eq ON orders (created_at, status);
```

#### Selectivity Considerations

For equality-only queries, column order matters less for correctness but can affect index size and scan efficiency. Place the most selective column first to narrow the search earliest.

```sql
-- If 'status' has 5 distinct values and 'country' has 200:
-- Better: more selective column first
CREATE INDEX idx_selective ON orders (country, status);
```

#### Sort Order Matching

For queries with `ORDER BY`, the index column order and sort direction must match:

```sql
-- Query: ORDER BY created_at DESC, id ASC
-- Index must match the sort directions
CREATE INDEX idx_sort ON orders (created_at DESC, id ASC);

-- This index CANNOT serve the above ORDER BY
CREATE INDEX idx_wrong_sort ON orders (created_at ASC, id ASC);
```

PostgreSQL can scan an index backward, so `(a ASC, b ASC)` can serve `ORDER BY a DESC, b DESC` but NOT `ORDER BY a DESC, b ASC`.

### 14. Index Advisor Tools

Several tools help identify missing indexes and unused indexes in PostgreSQL.

#### pg_stat_statements

Tracks query statistics including execution time and call count. Use to identify slow queries that might benefit from indexes:

```sql
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

#### auto_explain

Logs query plans for slow queries automatically:

```sql
ALTER SYSTEM SET auto_explain.log_min_duration = '100ms';
ALTER SYSTEM SET auto_explain.log_analyze = true;
SELECT pg_reload_conf();
```

#### HypoPG

Creates hypothetical indexes without actually building them, then runs `EXPLAIN` to see if the planner would use them:

```sql
SELECT * FROM hypopg_create_index('CREATE INDEX ON orders (customer_id, status)');
EXPLAIN SELECT * FROM orders WHERE customer_id = 123 AND status = 'active';
SELECT hypopg_drop_index(indexrelid) FROM hypopg_list_indexes();
```

This is invaluable for evaluating index strategies without the cost of building and testing real indexes on production data.

### General Rules

1. Start with no indexes beyond the primary key
2. Add indexes based on actual slow queries (EXPLAIN ANALYZE)
3. One well-chosen composite index beats multiple single-column indexes
4. Monitor index usage — remove unused indexes
5. Test index effectiveness with realistic data volumes (indexes behave differently at scale)
6. Use `CONCURRENTLY` for production index creation
7. Run `VACUUM` regularly to maintain index-only scan effectiveness
8. Profile with `pg_stat_statements` before and after adding indexes
9. Consider hypothetical index testing with HypoPG before committing
