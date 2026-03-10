---
id: d4567890-ef01-2345-6789-abcdef012345
date: 2026-02-10T09:00:00
type: insight
scope: general
title: "Immutable Infrastructure Principle"
tags: ["immutable-infrastructure", "devops", "deployment"]
related: ["[[20260210140000 Blue-Green vs Canary Deployments]]", "[[20260211100000 Configuration Drift Detection]]"]
summary: "Treating infrastructure as immutable eliminates configuration drift by replacing instances instead of updating them in place"
cb_source: hook-extraction
cb_created: 2026-02-10T09:00:00
---

## Immutable Infrastructure Principle

Instead of updating running servers (mutable infrastructure), build new images with the changes and replace the old instances entirely.

### Why It Matters

- Eliminates configuration drift (no snowflake servers)
- Deployments are atomic: the new version works or it doesn't
- Rollback is trivial: switch back to the old image
- Every deployment is a known-good state, not an accumulation of patches

### Requirements

- All state must be externalized (databases, object storage, not local disk)
- Build pipeline must be fast enough that rebuilding is practical
- Instance initialization must be automated (user data, cloud-init)

The principle applies at every layer: containers, VMs, and even network configuration.
