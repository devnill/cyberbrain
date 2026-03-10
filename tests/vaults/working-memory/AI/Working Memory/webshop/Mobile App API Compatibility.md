---
id: wm-d3333333-3333-3333-3333-333333333333
date: 2026-03-02T10:00:00
type: problem
scope: project
title: "Mobile App API Compatibility"
project: webshop
tags: ["mobile", "api", "compatibility", "versioning"]
related: []
summary: "Mobile app v2.3 still calls deprecated v1 API endpoints; need migration path before v1 sunset on April 1st"
cb_source: hook-extraction
cb_created: 2026-03-02T10:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_FUTURE_1
---

## Mobile App API Compatibility

### Problem

Mobile app version 2.3 (still 15% of active users) calls deprecated v1 API endpoints. v1 API sunset is scheduled for April 1st.

### Impact

- 15% of users (~45K) will experience broken app functionality after sunset
- App Store review takes 2-5 days — tight timeline for a forced update

### Options

1. **Force update**: require v2.4+ (has v2 API support) — bad UX but clean
2. **Extend v1**: keep v1 running for 3 more months — operational burden
3. **Compatibility layer**: proxy v1 calls to v2 endpoints — medium effort, transparent to users

### Recommendation

Option 3 (compatibility layer) buys time while pushing users to update naturally. Set v1 sunset to June 1st with deprecation headers starting now.
