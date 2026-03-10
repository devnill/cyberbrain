---
id: cc333333-3333-3333-3333-333333333333
date: 2026-02-12T10:30:00
type: problem
scope: project
title: "CSS-in-JS Performance Audit"
project: frontend-rewrite
tags: ["css", "performance", "styled-components", "frontend"]
related: []
summary: "styled-components runtime CSS injection caused layout thrashing on page navigation; migrated critical paths to CSS Modules"
cb_source: hook-extraction
cb_created: 2026-02-12T10:30:00
cb_lock: true
---

## CSS-in-JS Performance Audit

### Problem

Chrome DevTools Performance tab showed repeated "Recalculate Style" events during page navigation. Traced to styled-components injecting CSS at runtime.

### Root Cause

styled-components injects styles into the DOM via `<style>` tags at render time. Each new component adds style rules, triggering browser style recalculation. On pages with 100+ styled components, this adds 50-80ms of blocking time.

### Resolution

1. Migrated critical path components (layout, navigation) to CSS Modules (zero-runtime)
2. Kept styled-components for dynamic styling (theme-dependent, prop-dependent)
3. Enabled styled-components SSR `ServerStyleSheet` for server-rendered pages

### Results

- Style recalculation time: 80ms → 12ms on navigation
- Largest Contentful Paint: improved by ~200ms
