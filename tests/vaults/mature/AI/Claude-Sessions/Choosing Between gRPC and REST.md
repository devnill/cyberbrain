---
id: aa111111-1111-1111-1111-111111111111
date: 2026-01-10T09:00:00
type: decision
scope: general
title: "Choosing Between gRPC and REST"
project: general
tags: ["grpc", "rest", "api-design", "architecture"]
related: ["[[Protobuf Schema Management]]"]
summary: "Chose gRPC for internal service communication and REST for external APIs based on latency requirements and client ecosystem"
cb_source: hook-extraction
cb_created: 2026-01-10T09:00:00
---

## Choosing Between gRPC and REST

### Decision

- Internal service-to-service: gRPC (binary protocol, streaming, code generation)
- External APIs: REST/JSON (broad client support, human-readable, cURL-friendly)

### Rationale

gRPC's binary serialization and HTTP/2 multiplexing reduce internal call latency by ~40% compared to REST/JSON. Code-generated clients eliminate serialization bugs. But external consumers need REST because:

1. Browser support for gRPC is limited (requires grpc-web proxy)
2. API documentation tooling (Swagger/OpenAPI) is mature for REST
3. Third-party integrations expect REST endpoints
4. Debugging is harder with binary protocols

### Trade-off

We accept the complexity of maintaining two API surfaces (gRPC internal + REST external) in exchange for optimized internal communication.
