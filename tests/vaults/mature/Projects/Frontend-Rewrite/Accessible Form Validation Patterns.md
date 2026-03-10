---
id: cc444444-4444-4444-4444-444444444444
date: 2026-02-14T10:00:00
type: reference
scope: project
title: "Accessible Form Validation Patterns"
project: frontend-rewrite
tags: ["accessibility", "forms", "validation", "frontend", "a11y"]
related: ["[[React Server Components Migration]]"]
summary: "ARIA-compliant form validation patterns that announce errors to screen readers and maintain keyboard focus"
cb_source: hook-extraction
cb_created: 2026-02-14T10:00:00
---

## Accessible Form Validation Patterns

### Inline Validation

- Use `aria-invalid="true"` on invalid fields
- Associate error messages with `aria-describedby`
- Don't validate on blur alone (screen reader users may leave the field to check something)
- Validate on submit, then set focus to the first invalid field

### Error Summary

```html
<div role="alert" aria-live="polite">
  <h2>There were 2 errors with your submission</h2>
  <ul>
    <li><a href="#email">Email is required</a></li>
    <li><a href="#password">Password must be at least 8 characters</a></li>
  </ul>
</div>
```

### Key Rules

1. Error messages must be associated with the field (not just color-coded)
2. Focus management: move focus to error summary on submit, or to first invalid field
3. Live regions (`aria-live`) announce dynamic errors without requiring navigation
4. Never rely solely on color to indicate validation state
