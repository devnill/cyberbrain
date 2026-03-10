---
id: wm-b3333333-3333-3333-3333-333333333333
date: 2026-02-25T10:00:00
type: reference
scope: general
title: "Performance Budget Tracking"
tags: ["performance", "budget", "frontend", "web-vitals"]
related: []
summary: "Current web vitals vs performance budget targets; LCP is 400ms over budget on mobile"
cb_source: hook-extraction
cb_created: 2026-02-25T10:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_3
---

## Performance Budget Tracking

### Current vs Target

| Metric | Target | Desktop | Mobile |
|--------|--------|---------|--------|
| LCP | 2.5s | 1.8s | 2.9s |
| FID | 100ms | 45ms | 85ms |
| CLS | 0.1 | 0.05 | 0.08 |
| Total JS | 200KB | 180KB | 180KB |
| Total CSS | 50KB | 42KB | 42KB |

### Action Items

- LCP mobile: optimize hero image loading (responsive `srcset`, preload)
- Consider lazy-loading below-fold images on mobile
- Audit third-party scripts for render-blocking behavior
