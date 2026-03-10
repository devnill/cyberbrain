---
id: 12345678-9abc-def0-1234-56789abcdef0
date: 2026-02-12T14:00:00
type: reference
scope: general
title: "Correlation IDs Across Services"
tags: ["correlation-id", "tracing", "microservices", "observability"]
related: ["[[20260212090000 Structured Logging Best Practices]]"]
summary: "Propagate correlation IDs via HTTP headers and message metadata to trace requests across service boundaries"
cb_source: hook-extraction
cb_created: 2026-02-12T14:00:00
---

## Correlation IDs Across Services

### Generation

- Generated at the edge (API gateway or first service to receive the request)
- UUID v4 or ULID (sortable, includes timestamp)
- Passed via `X-Correlation-ID` header (or `X-Request-ID`)

### Propagation

- HTTP: forward the header on all downstream calls
- Message queues: include in message metadata/headers
- Background jobs: pass as job parameter

### Implementation

```python
# Middleware (Flask example)
@app.before_request
def ensure_correlation_id():
    g.correlation_id = request.headers.get(
        'X-Correlation-ID', str(uuid.uuid4())
    )

@app.after_request
def add_correlation_header(response):
    response.headers['X-Correlation-ID'] = g.correlation_id
    return response
```

Every log line and every outgoing request includes this ID, enabling end-to-end trace reconstruction from logs alone.
