---
id: f8a9b0c1-2d3e-4f5a-6b7c-d8e9f0a1b2c3
date: 2026-01-06T15:30:00
type: problem
scope: general
title: "XML Schema Quirks in Payment Gateway"
project: legacy-migration
tags: ["xml", "schema", "payment", "legacy", "migration"]
related: ["[[SOAP to REST Migration Lessons]]"]
summary: "Discovered undocumented XML schema behaviors in the legacy payment gateway where optional fields were actually required for certain transaction types"
cb_source: hook-extraction
cb_created: 2026-01-06T15:30:00
---

## XML Schema Quirks in Payment Gateway

### Problem

The WSDL defined `<merchantRef>` as `minOccurs="0"` (optional), but the payment processor rejected transactions without it for recurring billing. This wasn't in the schema, the documentation, or the integration guide.

### Discovery Process

1. REST migration tests passed with mock data
2. Staging tests against the real processor started failing at ~5% rate
3. Failures correlated with `transaction_type = "recurring"`
4. Packet capture showed the processor returning a custom SOAP fault code not in the WSDL

### Resolution

- Added conditional required field validation in the REST adapter
- Documented 7 similar "optional but actually required" fields discovered through production error mining
- Created a compatibility test suite that exercises all transaction types against the real sandbox

### Lesson

XML schemas describe structure, not business rules. Always test against the real endpoint, not just the schema.
