---
id: aa777777-7777-7777-7777-777777777777
date: 2026-01-25T14:30:00
scope: general
title: "SQLite WAL Mode Benefits"
project: general
related: []
cb_source: hook-extraction
cb_created: 2026-01-25T14:30:00
---

## SQLite WAL Mode Benefits

WAL (Write-Ahead Logging) mode allows concurrent reads during writes. Default journal mode blocks readers during writes.

Enable with: `PRAGMA journal_mode=WAL;`

Benefits: concurrent reads, better write performance, crash recovery.
Trade-off: WAL file can grow large if not checkpointed, slightly more complex backup.
