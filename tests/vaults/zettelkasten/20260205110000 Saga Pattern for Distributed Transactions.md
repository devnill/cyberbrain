---
id: 78901234-abcd-ef56-7890-123456789abc
date: 2026-02-05T11:00:00
type: reference
scope: general
title: "Saga Pattern for Distributed Transactions"
tags: ["saga", "distributed-transactions", "microservices", "patterns"]
related: ["[[20260201100000 Eventual Consistency Trade-offs]]", "[[20260205143000 Compensating Transactions Design]]", "[[20260207100000 Idempotency Keys for API Retries]]"]
summary: "Orchestration vs choreography sagas for managing distributed transactions across microservices"
cb_source: hook-extraction
cb_created: 2026-02-05T11:00:00
---

## Saga Pattern for Distributed Transactions

### Orchestration Saga

A central coordinator tells each service what to do. Easier to understand the flow, but the coordinator is a single point of failure and a coupling point.

### Choreography Saga

Each service publishes events and listens for events from others. No central coordinator, but the flow is harder to trace and debug.

### When to Use Which

- **Orchestration**: complex flows with many steps, need for centralized monitoring, business logic in the flow itself
- **Choreography**: simple flows (2-3 services), services are truly independent, team autonomy matters

Both require compensating transactions for rollback.
