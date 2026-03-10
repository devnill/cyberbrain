---
id: dd222222-2222-2222-2222-222222222222
date: 2026-02-22T14:00:00
type: reference
scope: project
title: "In-flight Refactor of Config Module"
project: myproject
tags: ["refactor", "config", "in-progress"]
related: []
summary: "Splitting the monolithic config.py into config_loader.py (file I/O) and config_schema.py (validation) to improve testability"
cb_source: hook-extraction
cb_created: 2026-02-22T14:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_PAST_2
---

## In-flight Refactor of Config Module

### Plan

1. Extract file I/O into `config_loader.py` (load, save, merge)
2. Extract schema validation into `config_schema.py` (defaults, type checks)
3. Keep `config.py` as the public API surface (re-exports from both)
4. Update tests to use the new modules directly

### Progress

- Steps 1-2 complete
- Step 3 in progress (updating import paths across 12 files)
- Step 4 not started
