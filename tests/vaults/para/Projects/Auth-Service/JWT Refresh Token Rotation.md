---
id: e5f6a7b8-9c0d-1e2f-3a4b-c5d6e7f8a9b0
date: 2026-02-18T11:20:00
type: decision
scope: project
title: "JWT Refresh Token Rotation"
project: auth-service
tags: ["jwt", "authentication", "security", "refresh-token"]
related: ["[[OAuth2 PKCE Flow for Mobile Clients]]"]
summary: "Implemented refresh token rotation with reuse detection to mitigate token theft while keeping stateless JWT access tokens"
cb_source: hook-extraction
cb_created: 2026-02-18T11:20:00
---

## JWT Refresh Token Rotation

### Decision

Implement refresh token rotation: each time a refresh token is used, issue a new refresh token and invalidate the old one. Detect reuse of invalidated tokens as a signal of token theft.

### Why Not Stateless Refresh Tokens

Stateless refresh tokens (long-lived JWTs) can't be individually revoked. If stolen, the attacker has access until expiry. Token rotation with a server-side family tracking provides:

- Automatic revocation on reuse detection
- Bounded window of vulnerability (one refresh interval)
- Audit trail of token usage patterns

### Implementation

- Refresh tokens stored in `refresh_tokens` table with `family_id` and `used` flag
- On refresh: mark current token as used, issue new token in same family
- If a used token is presented: revoke entire family (compromise detected)
- Access token TTL: 15 minutes. Refresh token TTL: 7 days.
