---
id: aa131313-1313-1313-1313-131313131313
date: 2026-01-14T11:00:00
type: insight
scope: general
title: "Testing Pyramid in Practice"
project: general
tags: ["testing", "test-pyramid", "quality", "architecture"]
related: []
summary: "The testing pyramid works for most services but inverts for UI-heavy apps where integration tests catch more real bugs than unit tests"
cb_source: hook-extraction
cb_created: 2026-01-14T11:00:00
---

## Testing Pyramid in Practice

The testing pyramid (many unit tests, fewer integration tests, few E2E tests) works well for backend services where business logic is in pure functions. But for UI-heavy applications, the pyramid inverts:

### Backend Services (traditional pyramid)

- Unit tests catch logic errors in business rules
- Integration tests verify database queries and API contracts
- E2E tests verify critical user journeys

### Frontend / UI-Heavy (inverted pyramid)

- Unit tests on components catch rendering bugs but miss interaction bugs
- Integration tests (component + state + routing) catch the majority of real bugs
- E2E tests (Playwright/Cypress) verify the full stack

The key insight: test at the level where bugs actually occur, not where tests are cheapest to write.
