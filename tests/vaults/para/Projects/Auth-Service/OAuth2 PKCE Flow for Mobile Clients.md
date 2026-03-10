---
id: f6a7b8c9-0d1e-2f3a-4b5c-d6e7f8a9b0c1
date: 2026-02-19T13:45:00
type: reference
scope: project
title: "OAuth2 PKCE Flow for Mobile Clients"
project: auth-service
tags: ["oauth2", "pkce", "mobile", "authentication"]
related: ["[[JWT Refresh Token Rotation]]"]
summary: "Implementation details for OAuth2 PKCE flow for mobile clients including code verifier generation and token exchange"
cb_source: hook-extraction
cb_created: 2026-02-19T13:45:00
---

## OAuth2 PKCE Flow for Mobile Clients

### Flow

1. Client generates `code_verifier` (43-128 char random string)
2. Client computes `code_challenge = BASE64URL(SHA256(code_verifier))`
3. Authorization request includes `code_challenge` and `code_challenge_method=S256`
4. Server stores `code_challenge` with the authorization code
5. Token exchange includes `code_verifier` — server re-computes and verifies

### Key Parameters

```
code_verifier: [A-Za-z0-9\-._~]{43,128}
code_challenge: BASE64URL(SHA256(code_verifier))
code_challenge_method: S256 (never plain in production)
```

### Security Notes

- PKCE replaces the client secret for public clients (mobile, SPA)
- The code verifier is never transmitted over the network until the token exchange
- Even if the authorization code is intercepted, the attacker can't exchange it without the verifier
- Always use S256 method — plain method provides no security benefit
