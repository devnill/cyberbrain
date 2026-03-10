---
id: wm-c3333333-3333-3333-3333-333333333333
date: 2026-03-04T10:00:00
type: insight
scope: general
title: "Infrastructure Cost Audit Notes"
tags: ["infrastructure", "cost", "aws", "optimization"]
related: []
summary: "AWS cost audit found 30% of spend is on unused or oversized resources; top savings: right-sizing RDS, deleting unused EBS volumes"
cb_source: hook-extraction
cb_created: 2026-03-04T10:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_FUTURE_3
---

## Infrastructure Cost Audit Notes

### Findings

| Category | Monthly Spend | Savings Opportunity |
|----------|--------------|-------------------|
| RDS (oversized) | $4,200 | $2,100 (right-size from db.r5.2xlarge to db.r5.xlarge) |
| EBS volumes (unused) | $800 | $800 (delete 15 unattached volumes) |
| NAT Gateway | $1,500 | $500 (consolidate VPCs) |
| EC2 Reserved | $6,000 | $1,800 (30% discount with 1-year reserved) |
| S3 lifecycle | $400 | $300 (move old logs to Glacier) |

### Priority Actions

1. Delete unattached EBS volumes (immediate, zero risk)
2. Right-size staging RDS instances (low risk, test first)
3. Purchase reserved instances for production EC2 (budget approval needed)
4. Implement S3 lifecycle policies for log buckets
