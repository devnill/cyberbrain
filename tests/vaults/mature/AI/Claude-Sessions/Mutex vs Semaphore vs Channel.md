---
id: aa202020-2020-2020-2020-202020202020
date: 2026-02-23T11:00:00
type: reference
scope: general
title: "Mutex vs Semaphore vs Channel"
project: general
tags: ["concurrency", "synchronization", "mutex", "semaphore"]
related: []
summary: "When to use mutex, semaphore, or channel-based synchronization depending on the concurrency pattern"
cb_source: hook-extraction
cb_created: 2026-02-23T11:00:00
---

## Mutex vs Semaphore vs Channel

### Mutex

- Protects a shared resource: only one goroutine/thread at a time
- Use when: multiple goroutines read/write the same data structure
- Pattern: lock, modify, unlock

### Semaphore

- Limits concurrent access to N (configurable)
- Use when: you want to limit parallelism (e.g., max 10 concurrent HTTP requests)
- Pattern: acquire, do work, release

### Channel (Go) / Queue

- Communicates data between goroutines
- Use when: you're transferring ownership of data, not protecting shared state
- Pattern: producer sends, consumer receives

### Decision Rule

- Protecting state → mutex
- Limiting concurrency → semaphore
- Transferring data → channel
- "Don't communicate by sharing memory; share memory by communicating" — Go proverb
