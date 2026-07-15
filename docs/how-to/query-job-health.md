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

## Compare exact attempts

Use an approved list of full AttemptKeys when you need a before-and-after
comparison. Do not substitute the newest rows: a scheduled or unrelated run
can finish while you investigate.

First [resolve the full AttemptKey](verify-production-deployment.md#4-resolve-the-full-attemptkey)
for each approved run. Replace the placeholders with those six numeric fields:

```sql
WITH attempts (
  phase_order,
  phase,
  workspace_id,
  job_id,
  job_run_id,
  repair_count,
  task_run_id,
  execution_count
) AS (
  SELECT * FROM VALUES
    (1, 'before', <workspace-id>, <job-id>, <before-parent-run-id>,
     <before-repair-count>, <before-task-run-id>, <before-execution-count>),
    (2, 'after', <workspace-id>, <job-id>, <after-parent-run-id>,
     <after-repair-count>, <after-task-run-id>, <after-execution-count>)
)
SELECT
  a.phase,
  CASE WHEN r.job_run_id IS NULL THEN 'MISSING' ELSE 'FOUND' END AS match_status,
  r.generated_at,
  r.captured_at,
  r.upstream_result_state,
  r.capture_status,
  r.staging_cleanup_status,
  r.invocation_status,
  r.elapsed_seconds,
  r.total_nodes,
  r.success_nodes,
  r.warning_nodes,
  r.failed_nodes,
  r.skipped_nodes
FROM attempts AS a
LEFT JOIN `<catalog>`.`<observability-schema>`.`dbt_run_health` AS r
  ON r.workspace_id = a.workspace_id
 AND r.job_id = a.job_id
 AND r.job_run_id = a.job_run_id
 AND r.repair_count = a.repair_count
 AND r.task_run_id = a.task_run_id
 AND r.execution_count = a.execution_count
ORDER BY a.phase_order;
```

Require one `FOUND` row for every phase. A `MISSING` row means at least one key
field is wrong or the attempt has not been captured; do not compare partial
results.

Use the same approved key values for the node comparison:

```sql
WITH attempts (
  phase_order,
  phase,
  workspace_id,
  job_id,
  job_run_id,
  repair_count,
  task_run_id,
  execution_count
) AS (
  SELECT * FROM VALUES
    (1, 'before', <workspace-id>, <job-id>, <before-parent-run-id>,
     <before-repair-count>, <before-task-run-id>, <before-execution-count>),
    (2, 'after', <workspace-id>, <job-id>, <after-parent-run-id>,
     <after-repair-count>, <after-task-run-id>, <after-execution-count>)
)
SELECT
  a.phase,
  CASE WHEN n.job_run_id IS NULL THEN 'MISSING' ELSE 'FOUND' END AS match_status,
  n.resource_type,
  n.node_name,
  n.status,
  n.execution_seconds,
  n.failures,
  n.rows_affected
FROM attempts AS a
LEFT JOIN `<catalog>`.`<observability-schema>`.`dbt_node_health` AS n
  ON n.workspace_id = a.workspace_id
 AND n.job_id = a.job_id
 AND n.job_run_id = a.job_run_id
 AND n.repair_count = a.repair_count
 AND n.task_run_id = a.task_run_id
 AND n.execution_count = a.execution_count
ORDER BY a.phase_order, n.resource_type, n.node_name;
```

The complete key prevents repair attempts and repeated task executions from
being combined accidentally. Publish sanitized results, not the identifiers in
the internal AttemptKey list. See the
[real four-stage comparison](../explanation/how-project-changes-appear-in-observability.md).

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
