---
id: cc222222-2222-2222-2222-222222222222
date: 2026-02-11T14:00:00
type: insight
scope: project
title: "Component Hydration Strategy"
project: frontend-rewrite
tags: ["hydration", "react", "performance", "frontend"]
related: ["[[React Server Components Migration]]"]
summary: "Progressive hydration reduces time-to-interactive by deferring hydration of below-fold components until they enter the viewport"
cb_source: hook-extraction
cb_created: 2026-02-11T14:00:00
---

## Component Hydration Strategy

### Insight

Full hydration on page load means every component becomes interactive simultaneously, which blocks the main thread. Progressive hydration defers non-critical components:

1. **Immediate**: navigation, search bar, primary CTA
2. **On viewport entry**: charts, data tables, secondary content
3. **On interaction**: dropdown menus, modal dialogs, tooltips

### Implementation

```tsx
const LazyChart = dynamic(() => import('./Chart'), {
  ssr: true,        // server-render the HTML
  loading: () => <ChartSkeleton />,
});

// Hydrate when visible
<IntersectionObserverWrapper>
  <LazyChart data={data} />
</IntersectionObserverWrapper>
```

### Results (measured)

- Time to interactive: 4.2s → 1.8s on mobile
- First input delay: 280ms → 45ms
- Total JS parsed on load: 890KB → 340KB
