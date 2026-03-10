---
id: wm-b2222222-2222-2222-2222-222222222222
date: 2026-02-22T14:00:00
type: problem
scope: project
title: "CDN Cache Purge Automation"
project: webshop
tags: ["cdn", "caching", "automation", "devops"]
related: []
summary: "Manual CDN cache purges after product updates are error-prone and slow; need automated purge on CMS publish"
cb_source: hook-extraction
cb_created: 2026-02-22T14:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_2
---

## CDN Cache Purge Automation

### Problem

Product managers update product images and descriptions in the CMS, but changes don't appear on the site for up to 4 hours (CDN TTL). They've been requesting manual purges via Slack, which takes 15-30 minutes of engineering time each.

### Proposed Solution

1. CMS publish hook sends webhook to our API
2. API extracts affected product URLs from the CMS payload
3. API calls CDN purge API for those specific URLs
4. Confirm purge completion and log the operation

### Considerations

- CDN API has rate limits (1000 purges/day)
- Batch purges for bulk CMS updates
- Fallback: reduce TTL on product pages from 4h to 30min
