---
id: f2a3b4c5-6d7e-8f9a-0b1c-d2e3f4a5b6c7
date: 2026-02-13T10:00:00
type: reference
scope: general
title: "Secrets Rotation Runbook"
project: security
tags: ["secrets", "rotation", "vault", "runbook"]
related: []
summary: "Step-by-step runbook for rotating database credentials, API keys, and TLS certificates"
cb_source: hook-extraction
cb_created: 2026-02-13T10:00:00
---

## Secrets Rotation Runbook

### Database Credentials (quarterly)

1. Generate new password in HashiCorp Vault: `vault write database/rotate-role/app-role`
2. Verify new credentials work: `psql -h db.internal -U app_user -d production`
3. Rolling restart of application pods: `kubectl rollout restart deployment/api`
4. Verify connections using new credentials in Grafana connection pool dashboard
5. Old password auto-expires after 24h grace period

### API Keys (on compromise or annually)

1. Generate new key in provider dashboard
2. Update in HashiCorp Vault: `vault kv put secret/integrations/stripe api_key=sk_live_...`
3. Restart affected services
4. Revoke old key in provider dashboard after confirming new key works

### TLS Certificates (auto-renewed via cert-manager)

- cert-manager handles renewal 30 days before expiry
- Monitor: `kubectl get certificates -A` should show `Ready=True`
- Manual renewal: `kubectl delete certificate <name>` to trigger re-issuance
