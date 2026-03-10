---
id: wm-c4444444-4444-4444-4444-444444444444
date: 2026-03-05T09:00:00
type: decision
scope: project
title: "A-B Testing Framework Evaluation"
project: webshop
tags: ["ab-testing", "experimentation", "evaluation", "webshop"]
related: []
summary: "Evaluating A/B testing frameworks: LaunchDarkly vs Optimizely vs custom solution for webshop experiments"
cb_source: hook-extraction
cb_created: 2026-03-05T09:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_FUTURE_4
---

## A-B Testing Framework Evaluation

### Options

| Feature | LaunchDarkly | Optimizely | Custom |
|---------|-------------|-----------|--------|
| Server-side flags | Yes | Yes | Build |
| Client-side SDK | Yes | Yes | Build |
| Statistical analysis | Basic | Advanced | Build |
| Audience targeting | Advanced | Advanced | Basic |
| Price (monthly) | $500 | $800 | Engineering time |
| Integration effort | 1 week | 1 week | 4-6 weeks |

### Leaning Toward

LaunchDarkly — we already use it for feature flags, adding experimentation is incremental. The statistical analysis is basic but sufficient for our experiment volume (2-3 concurrent tests).

### Pending

- Get pricing for our traffic volume (500K MAU)
- Verify server-side evaluation latency meets our <10ms budget
- Check if their JS SDK is compatible with our CSP policy
