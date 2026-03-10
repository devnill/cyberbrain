---
id: c3d4e5f6-7a8b-9c0d-1e2f-a3b4c5d6e7f8
date: 2026-02-20T09:00:00
type: problem
scope: project
title: "Gateway Timeout Cascading"
project: api-gateway
tags: ["timeout", "api-gateway", "circuit-breaker", "resilience"]
related: ["[[Rate Limiting Strategy]]"]
summary: "Gateway timeout of 30s caused cascading failures when downstream services were slow; resolved with per-route timeouts and circuit breaker"
cb_source: hook-extraction
cb_created: 2026-02-20T09:00:00
---

## Gateway Timeout Cascading

### Problem

The global 30-second gateway timeout caused cascading failures during a downstream service degradation. When the recommendation service started responding in 25-28 seconds, gateway threads were consumed waiting, which starved fast endpoints like health checks and auth.

### Investigation

- Thread pool exhaustion visible in metrics: active threads hit 200/200 limit
- Health check latency spiked from 2ms to 29s
- Load balancer marked instances unhealthy, triggering rolling restarts

### Resolution

1. Per-route timeout configuration: `/recommendations` gets 10s, `/auth` gets 3s, default 5s
2. Circuit breaker (Hystrix pattern) on downstream calls — open after 5 failures in 10s window
3. Bulkhead pattern: separate thread pools for critical vs. non-critical routes

### Lessons

- A single global timeout is never right for a gateway
- Health check endpoints must be isolated from business logic thread pools
- Circuit breakers need to be per-service, not per-route
