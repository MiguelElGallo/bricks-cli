---
icon: lucide/table-properties
---

# Observability objects

The collector owns three restricted Delta tables, two guaranteed sanitized
views, and three best-effort Lakeflow-backed views in the target-scoped
observability schema.

## Namespace

```text
<catalog>.<resolved-observability-schema>
```

The configured schema name is `${var.observability_schema}_${bundle.target}`;
development mode can additionally apply its resource prefix. Use
`databricks bundle summary` to obtain the resolved name.

## Availability contract

| Class | Objects | Guarantee |
|-------|---------|-----------|
| Restricted tables | `dbt_artifact_registry`, `dbt_invocations`, `dbt_node_results` | Created if absent before every sweep |
| Sanitized dbt views | `dbt_run_health`, `dbt_node_health` | Refreshed on every sweep, including after Jobs API discovery failure |
| Lakeflow-backed views | `lakeflow_job_run_health`, `lakeflow_dbt_task_run_health`, `dbt_job_health` | Best effort; require readable `system.lakeflow` tables |

Failure to create or refresh the three optional views does not fail artifact
capture. Existing optional views may remain from a previous successful refresh,
so consumers that require them must verify availability and freshness.

## `dbt_artifact_registry`

One row represents one [AttemptKey](attempt-key.md). Change Data Feed is enabled.

| Column | Type | Null | Meaning |
|--------|------|------|---------|
| `workspace_id` | `BIGINT` | no | Workspace key |
| `job_id` | `BIGINT` | no | Source job key |
| `job_run_id` | `BIGINT` | no | Parent job run key |
| `repair_count` | `INT` | no | Repair dimension |
| `task_run_id` | `BIGINT` | no | Concrete task run key |
| `execution_count` | `INT` | no | Execution dimension |
| `task_key` | `STRING` | no | Configured source task key |
| `upstream_result_state` | `STRING` | no | Jobs API task result normalized to lowercase or `unknown` |
| `capture_status` | `STRING` | no | Capture state |
| `capture_error_code` | `STRING` | yes | Allowlisted capture/discovery/validation code |
| `captured_at` | `TIMESTAMP` | no | Latest eligible registry merge time |
| `staging_cleanup_status` | `STRING` | no | `PENDING` or `DELETED` |
| `staging_cleanup_error_code` | `STRING` | yes | Allowlisted deletion failure |
| `staging_cleanup_updated_at` | `TIMESTAMP` | no | Latest cleanup update |
| `staging_deleted_at` | `TIMESTAMP` | yes | Successful deletion time |
| `archive_path` | `STRING` | yes | Restricted raw or quarantine path |
| `archive_sha256` | `STRING` | yes | SHA-256 of complete compressed archive bytes |
| `archive_bytes` | `BIGINT` | yes | Compressed archive size |
| `file_count` | `INT` | yes | Tar regular-file count observed by the scanner |
| `total_uncompressed_bytes` | `BIGINT` | yes | Sum of regular-file member sizes |
| `invocation_id` | `STRING` | yes | dbt invocation identifier for valid content |
| `dbt_version` | `STRING` | yes | Version read from run-results metadata |
| `adapter_type` | `STRING` | yes | Adapter read from manifest metadata |
| `manifest_schema_version` | `STRING` | yes | Accepted manifest schema URL |
| `run_results_schema_version` | `STRING` | yes | Accepted run-results schema URL |
| `parser_version` | `STRING` | no | Collector parser contract version |

Logical merge key:

```text
(workspace_id, job_id, job_run_id, repair_count, task_run_id, execution_count)
```

## `dbt_invocations`

One row represents one successfully parsed dbt invocation for an AttemptKey.
Change Data Feed is enabled.

| Column | Type | Null | Meaning |
|--------|------|------|---------|
| AttemptKey columns | mixed | no | Six columns defined in [AttemptKey](attempt-key.md) |
| `invocation_id` | `STRING` | no | Shared manifest/run-results invocation identifier |
| `generated_at` | `TIMESTAMP` | no | UTC dbt artifact generation time |
| `dbt_version` | `STRING` | no | dbt version |
| `adapter_type` | `STRING` | no | Adapter type or `unknown` |
| `command` | `STRING` | no | Allowlisted command or `unknown` |
| `invocation_status` | `STRING` | no | `success`, `warning`, or `failed` |
| `elapsed_seconds` | `DOUBLE` | no | Non-negative dbt invocation duration |
| `total_nodes` | `INT` | no | Parsed result rows |
| `success_nodes` | `INT` | no | `success`, `pass`, or `no-op` count |
| `warning_nodes` | `INT` | no | `warn` or `partial success` count |
| `failed_nodes` | `INT` | no | `error`, `fail`, or `runtime error` count |
| `skipped_nodes` | `INT` | no | `skipped` count |
| `manifest_sha256` | `STRING` | no | SHA-256 of manifest JSON bytes |
| `parser_version` | `STRING` | no | Parser contract version |
| `ingested_at` | `TIMESTAMP` | no | Collector merge time |

Logical merge key is the AttemptKey plus `invocation_id`.

## `dbt_node_results`

One row represents one allowlisted dbt result node. Change Data Feed is enabled.

| Column | Type | Null | Meaning |
|--------|------|------|---------|
| AttemptKey columns | mixed | no | Six identity columns |
| `invocation_id` | `STRING` | no | Parent invocation |
| `unique_id` | `STRING` | no | dbt node unique ID |
| `resource_type` | `STRING` | no | Manifest resource type or `unknown` |
| `node_name` | `STRING` | no | Manifest node name, falling back to `unique_id` |
| `status` | `STRING` | no | Accepted lowercase dbt node status |
| `execution_seconds` | `DOUBLE` | no | Non-negative execution duration |
| `compile_seconds` | `DOUBLE` | yes | Derived compile timing duration |
| `execute_seconds` | `DOUBLE` | yes | Derived execute timing duration |
| `failures` | `BIGINT` | yes | Integer dbt failures field |
| `rows_affected` | `BIGINT` | yes | Integer adapter-response count |
| `ingested_at` | `TIMESTAMP` | no | Collector merge time |

Logical merge key is the AttemptKey plus `invocation_id` and `unique_id`.

## Guaranteed view: `dbt_run_health`

This view left-joins the registry to invocation facts and excludes raw archive
paths, raw JSON, logs, messages, and SQL.

```text
workspace_id, job_id, job_run_id, repair_count, task_run_id,
execution_count, task_key, upstream_result_state,
capture_status, capture_error_code, captured_at,
staging_cleanup_status, staging_cleanup_error_code,
staging_cleanup_updated_at, staging_deleted_at, archive_sha256,
invocation_id, generated_at, dbt_version, adapter_type, command,
invocation_status, elapsed_seconds, total_nodes, success_nodes,
warning_nodes, failed_nodes, skipped_nodes
```

Rows exist for terminal and retryable registry states, including attempts with
no invocation facts.

## Guaranteed view: `dbt_node_health`

This view exposes node facts only when:

- registry status is `COMPLETE`;
- archive hash is present; and
- observed node count equals invocation `total_nodes`.

It exposes all `dbt_node_results` columns and no free-form dbt message, compiled
SQL, or adapter response object.

## Best-effort view: `lakeflow_job_run_health`

One row represents one configured source job run from the latest 365 days of
`system.lakeflow.job_run_timeline`.

```text
workspace_id, job_id, run_id, started_at, ended_at, active_seconds,
result_state, termination_code, trigger_type, run_type
```

It is scoped to the authenticated workspace ID and configured source job ID.

## Best-effort view: `lakeflow_dbt_task_run_health`

One row represents one configured task run from the latest 365 days of
`system.lakeflow.job_task_run_timeline`.

```text
workspace_id, job_id, job_run_id, task_run_id, task_key,
started_at, ended_at, active_seconds,
result_state, termination_code, termination_type
```

It is additionally scoped to `dbt_nyc_taxi`.

## Best-effort view: `dbt_job_health`

This view starts from native job runs, joins native task history, then joins dbt
evidence to the exact native `task_run_id`.

```text
workspace_id, job_id, job_run_id, started_at, ended_at, active_seconds,
result_state, termination_code, trigger_type, run_type,
native_task_run_id, task_result_state, task_termination_code,
task_termination_type, repair_count, task_run_id, execution_count,
capture_status, capture_error_code, staging_cleanup_status,
staging_cleanup_error_code, invocation_id, invocation_status,
dbt_elapsed_seconds, total_nodes, success_nodes, warning_nodes,
failed_nodes, skipped_nodes, evidence_status
```

The native run remains visible without dbt evidence as `MISSING` or `PENDING`.

## Example query

```sql
SELECT
  job_run_id,
  task_run_id,
  execution_count,
  capture_status,
  staging_cleanup_status,
  invocation_status,
  failed_nodes
FROM `<catalog>`.`<observability-schema>`.`dbt_run_health`
ORDER BY generated_at DESC;
```

For verified values from a real run, see the tutorial's
[verified sanitized capture](../tutorials/observe-your-first-run.md#see-one-real-reference-capture).

See the official [Lakeflow Jobs system-table reference](https://docs.databricks.com/aws/en/admin/system-tables/jobs).
