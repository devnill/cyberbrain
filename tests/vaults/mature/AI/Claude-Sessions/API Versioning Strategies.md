---
id: aaeeeeee-eeee-eeee-eeee-eeeeeeeeeeee
date: 2026-02-04T09:00:00
type: decision
scope: general
title: "API Versioning Strategies"
project: general
tags: ["api-versioning", "api-design", "architecture"]
related: ["[[Webhook Delivery Guarantees]]"]
summary: "Chose URL path versioning over header versioning for its simplicity, debuggability, and CDN cacheability"
cb_source: hook-extraction
cb_created: 2026-02-04T09:00:00
---

## API Versioning Strategies

### Options Evaluated

1. **URL path**: `/v1/users`, `/v2/users`
2. **Header**: `Accept: application/vnd.api+json; version=2`
3. **Query parameter**: `/users?version=2`

### Decision: URL path versioning

- Most explicit and discoverable
- CDN-cacheable without custom cache key configuration
- Easy to debug (version visible in URL)
- Easy to run both versions simultaneously behind the same gateway

### Trade-off

- URL changes when version changes (clients must update base URL)
- Resources have multiple URIs (one per version)
- Purists argue it's not RESTful (the resource is the same, the representation changes)
