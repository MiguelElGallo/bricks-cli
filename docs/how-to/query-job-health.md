---
icon: lucide/search-code
---

# Query job health

Use the sanitized Unity Catalog views for routine operations. Replace
`<catalog>` and `<observability-schema>` with the production values, such as
`dbt_observability_prod` for the schema created from the defaults.

## Check recent dbt runs

```sql
SELECT
  job_run_id,
  repair_count,
  task_run_id,
  execution_count,
  upstream_result_state,
  capture_status,
  staging_cleanup_status,
  invocation_status,
  failed_nodes,
  warning_nodes,
  elapsed_seconds,
  captured_at
FROM `<catalog>`.`<observability-schema>`.`dbt_run_health`
ORDER BY captured_at DESC
LIMIT 100;
```

A successful operational result normally has `capture_status = 'COMPLETE'` and
`staging_cleanup_status = 'DELETED'`. The upstream dbt result is independent: a
failed dbt attempt can still have complete evidence.

## Find captures that need action

```sql
SELECT
  workspace_id,
  job_id,
  job_run_id,
  repair_count,
  task_run_id,
  execution_count,
  upstream_result_state,
  capture_status,
  capture_error_code,
  staging_cleanup_status,
  staging_cleanup_error_code,
  captured_at
FROM `<catalog>`.`<observability-schema>`.`dbt_run_health`
WHERE capture_status IN ('QUARANTINED', 'NOT_PRODUCED',
                         'RETRYABLE_ERROR', 'UPLOAD_FAILED')
   OR staging_cleanup_status <> 'DELETED'
ORDER BY captured_at DESC;
```

`QUARANTINED` and `NOT_PRODUCED` are terminal evidence outcomes.
`RETRYABLE_ERROR` and `UPLOAD_FAILED` are non-terminal and should be retried by
a later collector sweep. Cleanup is tracked separately from capture.

## Find failed or warning nodes

```sql
SELECT
  job_run_id,
  repair_count,
  execution_count,
  resource_type,
  unique_id,
  status,
  failures,
  execution_seconds
FROM `<catalog>`.`<observability-schema>`.`dbt_node_health`
WHERE status IN ('warn', 'partial success', 'error', 'fail', 'runtime error')
ORDER BY ingested_at DESC, unique_id;
```

The view excludes dbt messages, compiled SQL, raw logs, and relation data.

## Correlate with Lakeflow Jobs when available

If the collector identity can read `system.lakeflow`, query the optional joined
view:

```sql
SELECT *
FROM `<catalog>`.`<observability-schema>`.`dbt_job_health`
ORDER BY ended_at DESC
LIMIT 100;
```

If that view does not exist, use `dbt_run_health` and the Databricks Jobs UI or
API. `SYSTEM_LAKEFLOW_VIEW_UNAVAILABLE` is a best-effort enrichment warning; it
does not mean artifact capture failed.

## Keep the evidence boundary intact

Operators should receive `SELECT` on the curated views only. The three base
tables and both Volumes contain more sensitive operational evidence and belong
to the collector boundary. See [Grant operator access](grant-operator-access.md).
