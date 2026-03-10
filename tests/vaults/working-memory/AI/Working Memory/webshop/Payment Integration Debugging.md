---
id: wm-a1111111-1111-1111-1111-111111111111
date: 2026-02-01T09:00:00
type: problem
scope: project
title: "Payment Integration Debugging"
project: webshop
tags: ["payment", "stripe", "debugging", "in-progress"]
related: []
summary: "Stripe webhook signature verification failing intermittently in staging; suspect clock skew between servers"
cb_source: hook-extraction
cb_created: 2026-02-01T09:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_PAST_1
---

## Payment Integration Debugging

Stripe webhook signature verification fails ~5% of the time in staging. The `stripe.Webhook.construct_event()` call throws `SignatureVerificationError`.

### Hypothesis

Clock skew between the load balancer and application servers. Stripe's tolerance is 300 seconds, but NTP drift on the staging cluster may exceed this.

### Evidence

- Failures correlate with requests hitting specific pods
- Those pods have been running for 30+ days without restart
- NTP service on the host nodes may have stalled

### Next Steps

- Check NTP status on affected hosts
- Add clock skew monitoring to the cluster
- If confirmed, add `chrony` to the base image
