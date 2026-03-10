---
id: 89012345-abcd-ef67-8901-23456789abcd
date: 2026-02-05T14:30:00
type: insight
scope: general
title: "Compensating Transactions Design"
tags: ["saga", "compensation", "distributed-systems", "error-handling"]
related: ["[[20260205110000 Saga Pattern for Distributed Transactions]]", "[[20260207100000 Idempotency Keys for API Retries]]"]
summary: "Compensating transactions are not undo operations — they are new forward actions that semantically reverse the effect of the original"
cb_source: hook-extraction
cb_created: 2026-02-05T14:30:00
---

## Compensating Transactions Design

A compensating transaction is not a rollback or an undo. It is a new, forward-moving transaction that semantically reverses the effect of the original.

### Example

- Original: "charge customer $50" → Compensation: "refund customer $50"
- Not: "delete the charge record" — the charge happened, the refund is a new event

### Design Rules

1. Compensations must be idempotent (may be retried on failure)
2. Compensations must handle the case where the original didn't complete (no-op)
3. Some operations are not compensatable (sending an email, calling an external API that doesn't support reversal)
4. Non-compensatable steps should be last in the saga

The ordering constraint is critical: place non-compensatable steps at the end of the saga so they only execute after all compensatable steps have succeeded.
