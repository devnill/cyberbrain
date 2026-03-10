---
id: bb222222-2222-2222-2222-222222222222
date: 2026-02-06T11:00:00
type: decision
scope: project
title: "Airflow Task Retry Strategy"
project: data-pipeline
tags: ["airflow", "retry", "data-pipeline", "reliability"]
related: ["[[Airflow DAG Design Patterns]]", "[[Airflow XCom Anti-patterns]]"]
summary: "Standardized retry configuration for Airflow tasks with exponential backoff and per-task-type defaults"
cb_source: hook-extraction
cb_created: 2026-02-06T11:00:00
---

## Airflow Task Retry Strategy

### Decision

Standardized retry defaults by task type:

| Task Type | Retries | Retry Delay | Max Retry Delay |
|-----------|---------|-------------|-----------------|
| API calls | 3 | 60s exponential | 10 min |
| Database writes | 2 | 30s exponential | 5 min |
| File operations | 1 | 30s | 30s |
| External service calls | 5 | 120s exponential | 30 min |

### Implementation

```python
default_args = {
    'retries': 3,
    'retry_delay': timedelta(seconds=60),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=10),
}
```

### Rationale

- API calls and external services need more retries due to transient failures
- Database writes should fail fast (retrying a constraint violation is pointless)
- Exponential backoff prevents thundering herd on service recovery
