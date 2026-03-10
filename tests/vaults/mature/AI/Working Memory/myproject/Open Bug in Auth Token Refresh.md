---
id: dd111111-1111-1111-1111-111111111111
date: 2026-02-20T09:00:00
type: problem
scope: project
title: "Open Bug in Auth Token Refresh"
project: myproject
tags: ["auth", "bug", "token-refresh", "in-progress"]
related: []
summary: "Auth token refresh fails silently when the refresh token has been rotated but the client still holds the old one"
cb_source: hook-extraction
cb_created: 2026-02-20T09:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_PAST_1
---

## Open Bug in Auth Token Refresh

The token refresh endpoint returns 401 instead of a specific error code when the refresh token has been rotated. The client interprets this as "invalid credentials" and redirects to login instead of triggering a re-authentication flow.

### Current Status

- Reproduced locally
- Root cause identified: the rotation check returns a generic 401 instead of a 403 with error code `token_rotated`
- Fix PR drafted but blocked on API versioning discussion
