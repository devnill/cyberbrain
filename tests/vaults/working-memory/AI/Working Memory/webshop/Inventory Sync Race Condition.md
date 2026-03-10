---
id: wm-a3333333-3333-3333-3333-333333333333
date: 2026-02-10T10:00:00
type: problem
scope: project
title: "Inventory Sync Race Condition"
project: webshop
tags: ["inventory", "race-condition", "concurrency", "bug"]
related: ["[[Payment Integration Debugging]]"]
summary: "Concurrent orders can oversell items because inventory check and decrement are not atomic"
cb_source: hook-extraction
cb_created: 2026-02-10T10:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_PAST_3
---

## Inventory Sync Race Condition

### Problem

Two concurrent orders for the last item in stock can both succeed because the inventory check (`SELECT quantity`) and decrement (`UPDATE quantity = quantity - 1`) are not in the same transaction.

### Reproduction

1. Set item quantity to 1
2. Send two concurrent purchase requests
3. Both succeed; quantity goes to -1

### Fix Options

1. `SELECT ... FOR UPDATE` (pessimistic locking) — blocks concurrent reads
2. Optimistic locking with version column — retry on conflict
3. `UPDATE ... WHERE quantity >= :needed RETURNING quantity` — atomic check-and-decrement

Option 3 is simplest and doesn't require retry logic.
