---
id: ee111111-1111-1111-1111-111111111111
date: 2026-01-05T09:00:00
type: reference
scope: general
title: "Outdated Docker Compose Setup"
project: general
tags: ["docker", "docker-compose", "deprecated"]
related: []
summary: "Old Docker Compose configuration that was replaced by Kubernetes manifests"
cb_source: hook-extraction
cb_created: 2026-01-05T09:00:00
---

## Outdated Docker Compose Setup

This configuration was used for local development before migrating to Kubernetes-based development environments.

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgres://localhost/mydb
```

Superseded by Tilt + Kubernetes manifests.
