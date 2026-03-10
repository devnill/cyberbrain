---
id: bb666666-6666-6666-6666-666666666666
date: 2026-02-10T15:00:00
type: decision
scope: project
title: "dbt vs Custom Python ETL"
project: data-pipeline
tags: ["dbt", "etl", "data-pipeline", "decision"]
related: ["[[Data Quality Checks Framework]]"]
summary: "Chose custom Python ETL over dbt for data pipeline because our sources require complex API integrations that dbt's SQL-first approach doesn't handle well"
cb_source: hook-extraction
cb_created: 2026-02-10T15:00:00
---

## dbt vs Custom Python ETL

### Decision

Stay with custom Python ETL pipeline (Airflow + Python scripts) instead of adopting dbt.

### Why Not dbt

- Our primary data sources are REST APIs, not databases — dbt assumes SQL-accessible sources
- Complex transformation logic (ML feature engineering) doesn't fit SQL well
- Team expertise is Python, not SQL + Jinja2
- dbt's value proposition (SQL-based transforms, documentation, testing) is strongest for warehouse-to-warehouse transforms, not API-to-warehouse

### What We Can Adopt from dbt

- The idea of "models" with explicit dependencies (we use Airflow DAG dependencies)
- Built-in data quality tests (we use Great Expectations instead)
- Documentation generation (we should build something similar)
