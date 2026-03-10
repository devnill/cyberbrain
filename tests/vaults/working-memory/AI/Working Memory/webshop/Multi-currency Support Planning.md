---
id: wm-c2222222-2222-2222-2222-222222222222
date: 2026-03-03T14:00:00
type: reference
scope: project
title: "Multi-currency Support Planning"
project: webshop
tags: ["currency", "internationalization", "planning", "webshop"]
related: []
summary: "Planning multi-currency support for EU expansion; need exchange rate service, price rounding rules, and tax implications"
cb_source: hook-extraction
cb_created: 2026-03-03T14:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_FUTURE_2
---

## Multi-currency Support Planning

### Requirements

1. Display prices in EUR, GBP, and USD
2. Exchange rates updated daily from ECB feed
3. Prices rounded to local conventions (EUR: 2 decimals, JPY: 0 decimals)
4. Orders stored in display currency AND base currency (USD) for reporting

### Open Questions

- Should we set fixed prices per currency (marketing control) or auto-convert?
- How to handle exchange rate changes for items in cart?
- VAT implications for EU customers (MOSS/OSS scheme)

### Technical Decisions Needed

- Currency conversion at display time vs at checkout time
- Rounding strategy (round-half-up, banker's rounding)
- Price cache invalidation when exchange rates update
