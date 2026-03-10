---
id: c5d6e7f8-9a0b-1c2d-3e4f-a5b6c7d8e9f0
date: 2026-01-15T11:00:00
type: reference
scope: general
title: "jq Cheatsheet"
project: tools
tags: ["jq", "json", "cli", "cheatsheet"]
related: []
summary: "Common jq patterns for JSON processing in shell scripts and debugging"
cb_source: hook-extraction
cb_created: 2026-01-15T11:00:00
---

## jq Cheatsheet

### Selection

```bash
jq '.key'                    # get field
jq '.nested.key'             # nested field
jq '.array[0]'               # first element
jq '.array[-1]'              # last element
jq '.array[2:5]'             # slice
```

### Filtering

```bash
jq '.[] | select(.status == "active")'     # filter array
jq '.[] | select(.age > 30)'               # numeric filter
jq '.[] | select(.name | test("^A"))'      # regex filter
```

### Transformation

```bash
jq '[.[] | {name, id}]'                    # reshape objects
jq 'map(.price * .quantity)'               # compute
jq 'group_by(.category) | map({key: .[0].category, count: length})'
```

### Output Control

```bash
jq -r '.name'                # raw string (no quotes)
jq -c '.'                    # compact output
jq -e '.key'                 # exit 1 if null
jq --arg v "$VAR" '.key == $v'  # shell variable
```
