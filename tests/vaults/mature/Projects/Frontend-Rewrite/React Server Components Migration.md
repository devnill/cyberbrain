---
id: cc111111-1111-1111-1111-111111111111
date: 2026-02-10T09:00:00
type: decision
scope: project
title: "React Server Components Migration"
project: frontend-rewrite
tags: ["react", "rsc", "nextjs", "frontend", "architecture"]
related: ["[[Component Hydration Strategy]]"]
summary: "Decided to incrementally adopt React Server Components in the dashboard, starting with data-heavy pages where SSR reduces client bundle size"
cb_source: hook-extraction
cb_created: 2026-02-10T09:00:00
---

## React Server Components Migration

### Decision

Incrementally adopt React Server Components (RSC) via Next.js App Router for the admin dashboard, starting with data-heavy pages.

### Rationale

- Dashboard pages fetch 5-10 API calls on load; RSC moves this to the server
- Client bundle reduced by ~40% for data-display pages (no client-side fetch libraries)
- Existing client-interactive components (forms, drag-and-drop) remain as Client Components

### Migration Strategy

1. Phase 1: Convert read-only data pages (analytics, reports) — 2 weeks
2. Phase 2: Convert list/detail pages with filters — 3 weeks
3. Phase 3: Evaluate remaining pages case-by-case

### Risks

- Team unfamiliar with RSC mental model (server/client boundary)
- Library compatibility (some React libraries don't support RSC)
- Caching strategy needs rethinking (server-side cache vs client-side SWR)
