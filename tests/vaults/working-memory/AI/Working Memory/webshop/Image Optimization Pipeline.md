---
id: wm-d1111111-1111-1111-1111-111111111111
date: 2026-02-28T14:00:00
type: reference
scope: project
title: "Image Optimization Pipeline"
project: webshop
tags: ["images", "optimization", "cdn", "performance"]
related: ["[[Performance Budget Tracking]]"]
summary: "Planning automated image optimization pipeline: WebP conversion, responsive srcset generation, and lazy loading"
cb_source: hook-extraction
cb_created: 2026-02-28T14:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_3
---

## Image Optimization Pipeline

### Current State

- Product images uploaded as full-resolution JPEGs (avg 2MB)
- No responsive variants — same image served to mobile and desktop
- No WebP/AVIF conversion

### Proposed Pipeline

1. Upload triggers Lambda function
2. Lambda generates variants: thumbnail (200px), medium (800px), large (1600px)
3. Each variant converted to WebP and JPEG (fallback)
4. `<picture>` element with `srcset` for responsive loading
5. Lazy loading via `loading="lazy"` for below-fold images

### Expected Impact

- Page weight reduction: ~60% for product listing pages
- LCP improvement: ~500ms on mobile (currently over budget)
