---
id: 6f789012-abcd-ef34-5678-901234567890
date: 2026-02-04T16:00:00
type: reference
scope: general
title: "Read Model Projection Patterns"
tags: ["cqrs", "projections", "read-model", "event-sourcing"]
related: ["[[20260203140000 CQRS Event Sourcing Synergy]]", "[[20260204100000 Event Store Schema Design]]"]
summary: "Three projection patterns for CQRS read models: synchronous inline, async via message bus, and catch-up subscription"
cb_source: hook-extraction
cb_created: 2026-02-04T16:00:00
---

## Read Model Projection Patterns

### 1. Synchronous (inline)

Update read model in the same transaction as the event write. Simple but couples read and write performance. Good for low-throughput systems.

### 2. Async via Message Bus

Publish events to a message bus (Kafka, RabbitMQ), consumers update read models. Decoupled but introduces eventual consistency and message ordering concerns.

### 3. Catch-up Subscription

Read model polls the event store for new events since its last checkpoint. Simple, no message bus dependency, but adds polling latency. Good for read models that tolerate seconds of delay.

Each pattern trades consistency latency against operational complexity.
