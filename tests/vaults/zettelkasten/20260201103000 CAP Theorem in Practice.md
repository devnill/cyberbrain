---
id: 2b3c4d5e-6f78-90ab-cdef-123456789012
date: 2026-02-01T10:30:00
type: reference
scope: general
title: "CAP Theorem in Practice"
tags: ["cap-theorem", "distributed-systems", "architecture"]
related: ["[[20260201100000 Eventual Consistency Trade-offs]]", "[[20260202090000 Network Partition Handling Strategies]]"]
summary: "CAP theorem is about choosing behavior during partitions, not about choosing two of three properties permanently"
cb_source: hook-extraction
cb_created: 2026-02-01T10:30:00
---

## CAP Theorem in Practice

The common "pick two of three" framing is wrong. CAP says: during a network partition, you must choose between consistency and availability. When there is no partition, you can have both.

### Practical Implications

- **CP systems** (e.g., ZooKeeper): refuse requests during partition → available when healthy, unavailable during partition
- **AP systems** (e.g., Cassandra): serve stale data during partition → always available, sometimes inconsistent
- Most real systems are neither pure CP nor pure AP — they make different choices for different operations
