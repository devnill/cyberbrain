---
id: 4d5e6f78-90ab-cdef-1234-567890123456
date: 2026-02-03T14:00:00
type: insight
scope: general
title: "CQRS Event Sourcing Synergy"
tags: ["cqrs", "event-sourcing", "architecture", "patterns"]
related: ["[[20260201100000 Eventual Consistency Trade-offs]]", "[[20260204100000 Event Store Schema Design]]", "[[20260204160000 Read Model Projection Patterns]]"]
summary: "CQRS and event sourcing are independent patterns that combine synergistically — event sourcing provides the audit trail CQRS needs for read model reconstruction"
cb_source: hook-extraction
cb_created: 2026-02-03T14:00:00
---

## CQRS Event Sourcing Synergy

CQRS (separate read and write models) and event sourcing (store events, not state) are often conflated but are independent patterns. They combine well because:

1. Event sourcing gives you a complete history of state changes
2. CQRS read models can be rebuilt from that history at any time
3. New read models can be added retroactively by replaying events

Without event sourcing, CQRS read models require careful synchronization with the write model. With event sourcing, the event stream is the synchronization mechanism.

The cost: event schema evolution is hard. Once an event is published, its schema is part of your public contract.
