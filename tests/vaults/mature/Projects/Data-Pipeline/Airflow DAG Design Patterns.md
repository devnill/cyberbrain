---
id: bb111111-1111-1111-1111-111111111111
date: 2026-02-05T09:00:00
type: reference
scope: project
title: "Airflow DAG Design Patterns"
project: data-pipeline
tags: ["airflow", "dag", "data-pipeline", "orchestration"]
related: ["[[Airflow Task Retry Strategy]]", "[[Airflow XCom Anti-patterns]]", "[[Airflow Dynamic DAG Generation]]"]
summary: "Design patterns for Airflow DAGs including task grouping, dependency management, and idempotent task design"
cb_source: hook-extraction
cb_created: 2026-02-05T09:00:00
---

## Airflow DAG Design Patterns

### 1. Idempotent Tasks

Every task should produce the same result regardless of how many times it runs. Use `INSERT ... ON CONFLICT UPDATE` instead of `INSERT`. Use date-partitioned tables so reruns overwrite the partition.

### 2. Task Granularity

- Too fine: excessive scheduler overhead, complex dependency graphs
- Too coarse: a single failure reruns expensive operations
- Sweet spot: each task is a logical unit of work that can be retried independently

### 3. Dependency Fan-out

Use `TaskGroup` for visual organization. Limit fan-out to ~20 parallel tasks to avoid scheduler overload.

### 4. Sensors

Avoid long-running sensors (they occupy a worker slot). Use `mode="reschedule"` instead of `mode="poke"` for sensors that may wait more than a few minutes.

### 5. Error Handling

- Use `on_failure_callback` for alerting, not for control flow
- Downstream tasks should handle missing data from upstream failures
- Set `depends_on_past=False` unless you genuinely need sequential execution
