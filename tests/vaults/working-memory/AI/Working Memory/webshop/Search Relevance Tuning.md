---
id: wm-a4444444-4444-4444-4444-444444444444
date: 2026-02-15T11:00:00
type: insight
scope: project
title: "Search Relevance Tuning"
project: webshop
tags: ["search", "elasticsearch", "relevance", "tuning"]
related: []
summary: "Boosting product name matches by 3x and adding synonym expansion improved search conversion by 12%"
cb_source: hook-extraction
cb_created: 2026-02-15T11:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_PAST_4
---

## Search Relevance Tuning

### Changes Made

1. Product name field boosted 3x over description
2. Added synonym expansion (e.g., "laptop" = "notebook")
3. Enabled fuzzy matching with edit distance 1 for typos
4. Added category facet boosting (user's browsing history category gets 1.5x boost)

### Results

- Search → product view conversion: 34% → 46% (+12pp)
- Zero-result searches: 8% → 3%
- Average position of clicked result: 4.2 → 2.1

### Still TODO

- Implement "did you mean" for misspellings
- Add personalized ranking based on purchase history
- Test re-ranking with a lightweight ML model
