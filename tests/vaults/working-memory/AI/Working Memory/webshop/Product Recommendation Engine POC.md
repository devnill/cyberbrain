---
id: wm-c1111111-1111-1111-1111-111111111111
date: 2026-03-02T09:00:00
type: reference
scope: project
title: "Product Recommendation Engine POC"
project: webshop
tags: ["recommendations", "ml", "poc", "webshop"]
related: ["[[Search Relevance Tuning]]"]
summary: "POC plan for collaborative filtering recommendations; using implicit signals (views, purchases) not explicit ratings"
cb_source: hook-extraction
cb_created: 2026-03-02T09:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_FUTURE_1
---

## Product Recommendation Engine POC

### Approach

Collaborative filtering using implicit feedback signals:
- Product views (weight: 1)
- Add to cart (weight: 3)
- Purchase (weight: 5)
- Return (weight: -3)

### Technology

- Python + scikit-surprise for prototyping
- ALS (Alternating Least Squares) for implicit feedback
- Batch retraining nightly, serve from Redis cache

### Success Criteria

- Recommendation click-through rate > 5%
- Revenue per session increase > 2%
- Latency: < 50ms per recommendation request (from Redis)

### Timeline

- Week 1: Data pipeline for implicit signals
- Week 2: Model training and offline evaluation
- Week 3: API endpoint and Redis caching
- Week 4: A/B test on product detail pages
