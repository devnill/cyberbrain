---
id: aa101010-1010-1010-1010-101010101010
date: 2026-02-06T10:00:00
type: insight
scope: general
title: "Error Handling Philosophy"
project: general
tags: ["error-handling", "philosophy", "architecture"]
related: ["[[Dependency Injection Without a Framework]]"]
summary: "Errors should be handled at the boundary where you have enough context to decide what to do, not at the point of occurrence"
cb_source: hook-extraction
cb_created: 2026-02-06T10:00:00
---

## Error Handling Philosophy

### The Rule

Handle errors at the boundary where you have enough context to make a decision:

1. **Library code**: raise specific exceptions, never catch and swallow
2. **Service layer**: catch domain exceptions, translate to service results
3. **API boundary**: catch service errors, translate to HTTP responses
4. **Global handler**: catch everything else, log and return 500

### Anti-patterns

- **Catch-and-ignore**: `except: pass` — hides bugs
- **Catch-and-re-raise the same exception**: adds noise without value
- **Catch Exception at every level**: obscures the real handling point
- **Return None on error**: forces callers to check for None everywhere

### Python-specific

Use custom exception hierarchies rooted in a common base:

```python
class AppError(Exception): ...
class NotFoundError(AppError): ...
class ValidationError(AppError): ...
class AuthorizationError(AppError): ...
```

API boundary catches `AppError` and maps to HTTP status codes. Everything else gets a 500.
