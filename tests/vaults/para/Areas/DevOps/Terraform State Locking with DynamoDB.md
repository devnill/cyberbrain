---
id: b8c9d0e1-2f3a-4b5c-6d7e-f8a9b0c1d2e3
date: 2026-02-10T15:00:00
type: reference
scope: general
title: "Terraform State Locking with DynamoDB"
project: devops
tags: ["terraform", "dynamodb", "state-management", "aws"]
related: []
summary: "Configuration for Terraform state locking using DynamoDB to prevent concurrent modifications"
cb_source: hook-extraction
cb_created: 2026-02-10T15:00:00
---

## Terraform State Locking with DynamoDB

### Backend Configuration

```hcl
terraform {
  backend "s3" {
    bucket         = "company-terraform-state"
    key            = "services/api-gateway/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

### DynamoDB Table

- Table name: `terraform-locks`
- Partition key: `LockID` (String)
- Billing: on-demand (locks are infrequent)
- No sort key needed

### Lock Behavior

- `terraform plan` acquires a read lock (advisory)
- `terraform apply` acquires an exclusive lock
- Lock info includes: who, when, operation type
- Force-unlock: `terraform force-unlock <LOCK_ID>` (dangerous, use only when stuck)

### Gotchas

- DynamoDB table must exist before first `terraform init`
- State file and lock table should be in the same AWS account
- Cross-account state access requires IAM role assumption in the backend config
