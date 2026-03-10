---
id: aa888888-8888-8888-8888-888888888888
date: 2026-02-01T10:00:00
type: reference
scope: general
title: "Cursor Pagination for Large Datasets"
project: general
cb_source: hook-extraction
cb_created: 2026-02-01T10:00:00
---

## Cursor Pagination for Large Datasets

Offset-based pagination degrades on large tables because the database must scan and discard offset rows. Cursor-based pagination uses a pointer to the last seen record.

```sql
-- Offset (slow at high offsets)
SELECT * FROM orders ORDER BY id LIMIT 20 OFFSET 10000;

-- Cursor (constant time)
SELECT * FROM orders WHERE id > :last_seen_id ORDER BY id LIMIT 20;
```

Requires a unique, sortable column. Works with composite cursors (created_at + id) for non-unique sort columns.
