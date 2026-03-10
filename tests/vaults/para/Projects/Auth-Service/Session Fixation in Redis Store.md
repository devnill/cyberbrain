---
id: a7b8c9d0-1e2f-3a4b-5c6d-e7f8a9b0c1d2
date: 2026-02-21T08:30:00
type: problem
scope: project
title: "Session Fixation in Redis Store"
project: auth-service
tags: ["security", "session-fixation", "redis", "authentication"]
related: ["[[JWT Refresh Token Rotation]]"]
summary: "Session IDs were not regenerated after authentication, allowing session fixation attacks via pre-authentication session injection"
cb_source: hook-extraction
cb_created: 2026-02-21T08:30:00
---

## Session Fixation in Redis Store

### Problem

During a security audit, we found that session IDs were not regenerated after successful authentication. An attacker could:

1. Obtain a valid unauthenticated session ID
2. Trick a user into authenticating with that session ID
3. Use the now-authenticated session

### Root Cause

The session middleware was reusing the existing session ID across the authentication boundary. The Redis store preserved the session data including the session ID through the login flow.

### Fix

- Regenerate session ID on every authentication state change (login, logout, privilege escalation)
- Copy session data to new key, delete old key atomically via `RENAME` + `DEL`
- Set `__regenerated_at` timestamp in session data for audit
- Added integration test that verifies session ID changes after login
