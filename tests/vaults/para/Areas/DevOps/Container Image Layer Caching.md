---
id: c9d0e1f2-3a4b-5c6d-7e8f-a9b0c1d2e3f4
date: 2026-02-12T09:30:00
type: insight
scope: general
title: "Container Image Layer Caching"
project: devops
tags: ["docker", "caching", "ci-cd", "performance"]
related: []
summary: "Reordering Dockerfile instructions to maximize layer cache hits reduced CI build times by 60 percent"
cb_source: hook-extraction
cb_created: 2026-02-12T09:30:00
---

## Container Image Layer Caching

### Observation

Our CI builds were taking 8-12 minutes because every code change invalidated the entire Docker image cache. The Dockerfile copied source code early, which invalidated all subsequent layers including dependency installation.

### Fix

Reorder Dockerfile to maximize cache hits:

```dockerfile
# 1. Base image (rarely changes)
FROM python:3.11-slim

# 2. System deps (rarely changes)
RUN apt-get update && apt-get install -y --no-install-recommends gcc

# 3. Python deps (changes when requirements change)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 4. Source code (changes every commit)
COPY . .
```

### Results

- Build time: 8-12 min down to 2-3 min (cache hit on deps)
- Full rebuild (requirements change): still 8-12 min but happens weekly not per-commit
- CI cache storage: using `--cache-from` with ECR to share layers across builds
