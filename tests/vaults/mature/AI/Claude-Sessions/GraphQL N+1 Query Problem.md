---
id: aa999999-9999-9999-9999-999999999999
date: 2026-02-02T10:00:00
type: problem
scope: general
title: "GraphQL N+1 Query Problem"
project: general
tags: ["graphql", "performance", "dataloader", "database"]
related: ["[[Cursor Pagination for Large Datasets]]"]
summary: "GraphQL resolvers executing individual database queries per field caused N+1 query explosion; resolved with DataLoader batching"
cb_source: hook-extraction
cb_created: 2026-02-02T10:00:00
---

## GraphQL N+1 Query Problem

### Problem

A query for 50 users with their orders generated 51 SQL queries: 1 for users, then 1 per user for orders.

### Fix: DataLoader

DataLoader collects individual load calls within a single tick, then executes a single batched query:

```python
class OrderLoader(DataLoader):
    async def batch_load_fn(self, user_ids):
        orders = await db.fetch_all(
            "SELECT * FROM orders WHERE user_id = ANY($1)", user_ids
        )
        return [
            [o for o in orders if o.user_id == uid]
            for uid in user_ids
        ]
```

51 queries → 2 queries. DataLoader instances must be per-request (they cache within a request scope).
