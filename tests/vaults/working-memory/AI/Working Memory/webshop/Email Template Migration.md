---
id: wm-b1111111-1111-1111-1111-111111111111
date: 2026-02-20T09:00:00
type: reference
scope: project
title: "Email Template Migration"
project: webshop
tags: ["email", "templates", "migration", "in-progress"]
related: []
summary: "Migrating email templates from hardcoded HTML to MJML framework; 7 of 15 templates converted"
cb_source: hook-extraction
cb_created: 2026-02-20T09:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_1
---

## Email Template Migration

### Status

Migrating from inline HTML email templates to MJML (responsive email framework).

| Template | Status |
|----------|--------|
| Order confirmation | Done |
| Shipping notification | Done |
| Password reset | Done |
| Welcome email | Done |
| Cart reminder | Done |
| Refund confirmation | Done |
| Account verification | Done |
| Return label | In Progress |
| Review request | Not Started |
| Loyalty points | Not Started |
| Newsletter | Not Started |
| Promotional | Not Started |
| Wishlist alert | Not Started |
| Back in stock | Not Started |
| Payment failed | Not Started |

### Blockers

- MJML doesn't support Outlook 2019 conditional comments natively
- Need to test with Litmus before deploying each batch
