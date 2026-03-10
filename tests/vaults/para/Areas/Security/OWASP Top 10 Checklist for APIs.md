---
id: e1f2a3b4-5c6d-7e8f-9a0b-c1d2e3f4a5b6
date: 2026-02-08T14:00:00
type: reference
scope: general
title: "OWASP Top 10 Checklist for APIs"
project: security
tags: ["owasp", "api-security", "checklist", "security"]
related: ["[[Session Fixation in Redis Store]]"]
summary: "Condensed OWASP API Security Top 10 checklist with our current mitigation status"
cb_source: hook-extraction
cb_created: 2026-02-08T14:00:00
---

## OWASP Top 10 Checklist for APIs

| # | Risk | Status | Mitigation |
|---|------|--------|-----------|
| 1 | Broken Object Level Auth | Partial | Per-resource ownership checks in service layer |
| 2 | Broken Authentication | Done | PKCE + refresh rotation + session regen |
| 3 | Broken Object Property Auth | Partial | Response filtering in serializers |
| 4 | Unrestricted Resource Consumption | Done | Rate limiting via token bucket |
| 5 | Broken Function Level Auth | Done | RBAC middleware + route-level annotations |
| 6 | Unrestricted Access to Sensitive Flows | Partial | CAPTCHA on registration, missing on password reset |
| 7 | Server Side Request Forgery | Done | Egress allowlist + URL validation |
| 8 | Security Misconfiguration | Partial | Hardened headers, need CSP audit |
| 9 | Improper Inventory Management | Not Started | No API catalog or deprecation tracking |
| 10 | Unsafe Consumption of APIs | Partial | Input validation on webhook payloads |
