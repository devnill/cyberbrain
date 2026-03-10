---
id: 56789abc-def0-1234-5678-9abcdef01234
date: 2026-02-16T09:00:00
type: problem
scope: general
title: "DNS Caching Pitfall in Long-lived Processes"
tags: ["dns", "caching", "networking", "debugging"]
related: ["[[20260211100000 Configuration Drift Detection]]"]
summary: "Long-lived Python processes cached DNS resolutions indefinitely, causing failures when AWS RDS performed a failover and the endpoint IP changed"
cb_source: hook-extraction
cb_created: 2026-02-16T09:00:00
---

## DNS Caching Pitfall in Long-lived Processes

### Problem

After an RDS failover, application pods continued connecting to the old primary (now a read replica) because Python's `socket.getaddrinfo` results were cached in the connection pool's resolved address.

### Root Cause

- The database connection pool resolved the DNS name once at pool creation
- Connection recycling reused the resolved IP, not the DNS name
- RDS failover updates the DNS CNAME, but the application never re-resolved

### Fix

1. Set connection pool `max_lifetime` to 300s (force reconnection periodically)
2. Use `dns.resolver` with explicit TTL respect instead of system resolver
3. In Kubernetes: set `dnsConfig.options` with `ndots:1` and low `timeout` to avoid resolution delays

### Lesson

Any system that resolves DNS once and caches the result will break during a DNS-based failover. Always honor DNS TTL or set a maximum connection lifetime.
