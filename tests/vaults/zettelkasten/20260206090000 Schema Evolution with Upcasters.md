---
id: 90123456-abcd-ef78-9012-3456789abcde
date: 2026-02-06T09:00:00
type: reference
scope: general
title: "Schema Evolution with Upcasters"
tags: ["event-sourcing", "schema-evolution", "versioning"]
related: ["[[20260204100000 Event Store Schema Design]]", "[[20260203140000 CQRS Event Sourcing Synergy]]"]
summary: "Upcaster pattern for evolving event schemas without migrating historical events in the store"
cb_source: hook-extraction
cb_created: 2026-02-06T09:00:00
---

## Schema Evolution with Upcasters

An upcaster transforms an old event version to a new version at read time, avoiding the need to migrate stored events.

```python
def upcast_order_placed_v1_to_v2(event_data):
    """V1 had 'amount', V2 split into 'subtotal' + 'tax'."""
    return {
        "subtotal": event_data["amount"],
        "tax": 0,  # V1 didn't track tax separately
        **{k: v for k, v in event_data.items() if k != "amount"}
    }
```

### Rules

- Upcasters are pure functions (old data in, new data out)
- Chain upcasters: v1 → v2 → v3 (each step is a simple transform)
- Store events in their original version — upcasting happens on read
- Upcasters must be backward-compatible: never break an older upcaster
