---
id: 01234567-89ab-cdef-0123-456789abcdef
date: 2026-02-12T09:00:00
type: reference
scope: general
title: "Structured Logging Best Practices"
tags: ["logging", "observability", "json", "debugging"]
related: ["[[20260212140000 Correlation IDs Across Services]]", "[[20260209100000 Queue Depth as Health Signal]]"]
summary: "Structured logging rules: use JSON, include correlation IDs, log at boundaries, avoid PII, and keep log levels meaningful"
cb_source: hook-extraction
cb_created: 2026-02-12T09:00:00
---

## Structured Logging Best Practices

### Format

Always JSON. Never unstructured text. JSON logs are parseable by log aggregators without custom regex.

### Required Fields

```json
{
  "timestamp": "2026-02-12T09:00:00Z",
  "level": "info",
  "service": "api-gateway",
  "correlation_id": "abc-123",
  "message": "Request completed",
  "duration_ms": 145,
  "status_code": 200
}
```

### Rules

1. Log at service boundaries (incoming request, outgoing call, response)
2. Include correlation ID in every log line
3. Never log PII (emails, passwords, tokens) — use redaction middleware
4. Use log levels correctly: ERROR = needs human attention, WARN = degraded but functioning, INFO = business events, DEBUG = developer diagnostics
5. Include enough context to debug without reproducing (request ID, user ID, relevant parameters)
