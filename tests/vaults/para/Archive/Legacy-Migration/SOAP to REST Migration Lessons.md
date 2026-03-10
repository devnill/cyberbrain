---
id: e7f8a9b0-1c2d-3e4f-5a6b-c7d8e9f0a1b2
date: 2026-01-05T10:00:00
type: insight
scope: general
title: "SOAP to REST Migration Lessons"
project: legacy-migration
tags: ["migration", "soap", "rest", "legacy"]
related: []
summary: "Lessons learned from migrating a SOAP-based payment service to REST over 6 months, including the strangler fig approach and dual-write pitfalls"
cb_source: hook-extraction
cb_created: 2026-01-05T10:00:00
---

## SOAP to REST Migration Lessons

### What Worked

1. **Strangler fig pattern** — new endpoints in REST, old ones proxied to SOAP backend. Gradual migration without a big bang cutover.
2. **Contract tests** — Pact tests between old SOAP consumers and new REST endpoints caught 12 behavioral differences before production.
3. **Feature flags** — traffic splitting at the load balancer level (10%, 50%, 100%) with instant rollback.

### What Didn't

1. **Dual writes** — attempting to write to both old and new databases simultaneously led to consistency bugs. Switched to event-driven replication.
2. **Schema mapping underestimation** — SOAP's XML schema had implicit business rules (required fields that were only conditionally required) that weren't in any documentation.
3. **Client migration timeline** — assumed all clients would migrate in 3 months. Took 14 months. The long tail of old clients needs active management.

### Key Takeaway

The migration itself was the easy part. The hard part was discovering undocumented behavior in the SOAP service that clients depended on.
