---
id: bb444444-4444-4444-4444-444444444444
date: 2026-02-08T10:00:00
type: reference
scope: project
title: "Airflow Dynamic DAG Generation"
project: data-pipeline
tags: ["airflow", "dynamic-dag", "data-pipeline", "automation"]
related: ["[[Airflow DAG Design Patterns]]"]
summary: "Pattern for generating Airflow DAGs dynamically from configuration files to avoid boilerplate DAG definitions"
cb_source: hook-extraction
cb_created: 2026-02-08T10:00:00
---

## Airflow Dynamic DAG Generation

### Pattern

Instead of writing one Python file per DAG, generate DAGs from a YAML config:

```yaml
# dag_configs/etl_jobs.yaml
- name: users_etl
  schedule: "0 2 * * *"
  source: postgres.users
  destination: bigquery.analytics.users

- name: orders_etl
  schedule: "0 3 * * *"
  source: postgres.orders
  destination: bigquery.analytics.orders
```

```python
# dags/generated_etl.py
configs = yaml.safe_load(open("dag_configs/etl_jobs.yaml"))
for config in configs:
    dag = create_etl_dag(config)
    globals()[config["name"]] = dag
```

### Benefits

- Adding a new ETL job = adding a YAML entry (no Python)
- Consistent task structure across all generated DAGs
- Easy to audit what's running

### Risks

- Dynamic DAGs are harder to debug (no static file to inspect)
- Errors in config affect all generated DAGs
- Airflow's DAG discovery scans must be fast (don't read from external APIs at import time)
