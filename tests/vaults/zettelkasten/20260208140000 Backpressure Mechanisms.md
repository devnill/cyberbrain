---
id: b2345678-cdef-0123-4567-89abcdef0123
date: 2026-02-08T14:00:00
type: insight
scope: general
title: "Backpressure Mechanisms"
tags: ["backpressure", "queues", "distributed-systems", "flow-control"]
related: ["[[20260202090000 Network Partition Handling Strategies]]", "[[20260209100000 Queue Depth as Health Signal]]"]
summary: "Backpressure is the only sustainable way to handle producer-consumer speed mismatches — buffering without backpressure just delays the failure"
cb_source: hook-extraction
cb_created: 2026-02-08T14:00:00
---

## Backpressure Mechanisms

Unbounded buffers between producer and consumer don't solve speed mismatches — they convert sudden failures into gradual memory exhaustion. Backpressure propagates the slowdown upstream.

### Implementation Strategies

1. **Blocking** — producer blocks when buffer is full (simplest, worst for latency)
2. **Dropping** — drop oldest or newest when buffer is full (good for metrics, bad for transactions)
3. **Rate limiting** — limit producer emission rate based on consumer capacity
4. **Credit-based** — consumer grants credits to producer (Reactive Streams, TCP flow control)

The right choice depends on whether data loss is acceptable and whether the producer can be slowed.
