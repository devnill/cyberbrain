---
id: aa171717-1717-1717-1717-171717171717
date: 2026-02-18T09:00:00
type: reference
scope: general
title: "Python Type Hints Best Practices"
project: general
tags: ["python", "type-hints", "mypy", "code-quality"]
related: ["[[Dependency Injection Without a Framework]]", "[[Error Handling Philosophy]]"]
summary: "Practical type hinting guidelines for Python including when to use Protocol vs ABC and how to handle optional types"
cb_source: hook-extraction
cb_created: 2026-02-18T09:00:00
---

## Python Type Hints Best Practices

### Basics

- Use `str | None` (Python 3.10+) instead of `Optional[str]`
- Use `list[str]` instead of `List[str]` (Python 3.9+)
- Use `dict[str, Any]` for flexible dicts, specific types when structure is known

### Protocol vs ABC

- **Protocol**: structural subtyping ("if it has these methods, it works")
- **ABC**: nominal subtyping ("must explicitly inherit from this class")
- Prefer Protocol for dependency injection — it doesn't require implementation classes to know about the interface

### When Not to Type

- Lambda expressions (type inference handles it)
- `self` and `cls` parameters
- Test code (unless testing type-related behavior)
- Local variables where the type is obvious from assignment
