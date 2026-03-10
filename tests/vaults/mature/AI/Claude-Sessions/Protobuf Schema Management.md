---
id: aa222222-2222-2222-2222-222222222222
date: 2026-01-11T14:00:00
type: reference
scope: general
title: "Protobuf Schema Management"
project: general
tags: ["protobuf", "grpc", "schema", "versioning"]
related: ["[[Choosing Between gRPC and REST]]"]
summary: "Protobuf schema management rules: required fields are forever, use field numbers wisely, never reuse deleted field numbers"
cb_source: hook-extraction
cb_created: 2026-01-11T14:00:00
---

## Protobuf Schema Management

### Rules

1. **Never remove or rename fields** — mark as `reserved` instead
2. **Never reuse field numbers** — add new fields with new numbers
3. **Use `optional` keyword** for fields that may not be set (proto3)
4. **Group related fields** into nested messages for clarity
5. **Document every field** with comments

### Field Number Ranges

- 1-15: single-byte encoding, use for frequently set fields
- 16-2047: two-byte encoding, fine for most fields
- 19000-19999: reserved by protobuf implementation

### Breaking vs Non-breaking Changes

| Change | Safe? |
|--------|-------|
| Add field | Yes |
| Remove field (reserve number) | Yes |
| Rename field | Yes (wire format uses numbers) |
| Change field type | No |
| Change field number | No |
| Remove `reserved` | No |
