---
id: wm-d2222222-2222-2222-2222-222222222222
date: 2026-03-01T14:00:00
type: reference
scope: general
title: "Dependency Upgrade Audit"
tags: ["dependencies", "security", "audit", "maintenance"]
related: []
summary: "Quarterly dependency audit results: 3 critical CVEs, 12 outdated packages, 2 deprecated libraries"
cb_source: hook-extraction
cb_created: 2026-03-01T14:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_4
---

## Dependency Upgrade Audit

### Critical CVEs

1. `lodash` 4.17.20 → 4.17.21 (prototype pollution, CVE-2021-23337)
2. `express` 4.17.1 → 4.18.2 (open redirect, CVE-2024-29041)
3. `jsonwebtoken` 8.5.1 → 9.0.2 (algorithm confusion, CVE-2022-23529)

### Deprecated Libraries

- `request` → migrate to `node-fetch` or `undici`
- `moment` → migrate to `date-fns` or `dayjs`

### Plan

1. Patch critical CVEs this sprint (1 day of work)
2. Schedule deprecated library migration for next sprint
3. Enable Dependabot for automated PR creation
