---
id: bb555555-5555-5555-5555-555555555555
date: 2026-02-09T15:00:00
type: decision
scope: project
title: "Data Quality Checks Framework"
project: data-pipeline
tags: ["data-quality", "testing", "data-pipeline", "great-expectations"]
related: ["[[Airflow DAG Design Patterns]]"]
summary: "Chose Great Expectations over custom validation for data quality checks based on its built-in profiling and documentation features"
cb_source: hook-extraction
cb_created: 2026-02-09T15:00:00
---

## Data Quality Checks Framework

### Decision

Adopt Great Expectations for data quality validation in the ETL pipeline instead of custom validation scripts.

### Alternatives

1. **Custom scripts**: full control, but we'd reinvent profiling, documentation, and alerting
2. **Great Expectations**: opinionated but covers 90% of our needs out of the box
3. **dbt tests**: good for SQL-based checks, but our pipeline is Python-heavy

### What We Get

- Automatic data profiling from sample datasets
- Expectation suites versioned alongside code
- Data docs (HTML reports) generated automatically
- Integration with Airflow via `GreatExpectationsOperator`

### Compromise

Great Expectations has a learning curve and adds ~30s to pipeline runtime per checkpoint. Acceptable for daily batch jobs, would need review for real-time pipelines.
