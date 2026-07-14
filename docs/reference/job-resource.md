---
icon: lucide/briefcase
---

# The dbt job resources

Two resource files define independent serverless Lakeflow jobs:

1. `resources/nyc_taxi.job.yml` defines `nyc_taxi_dbt_job`, which runs dbt and
   stages its JSON artifacts.
2. `resources/dbt_observability_collector.job.yml` defines
   `dbt_observability_collector_job`, which captures artifacts after source runs
   are complete.

`resources/observability.infrastructure.yml` defines the target-scoped Unity
Catalog schema plus separate staging and evidence managed Volumes.

## Source job: `nyc_taxi_dbt_job`

| Field | Committed value | Meaning |
|-------|-----------------|---------|
| `name` | `nyc_taxi_dbt_job` | Display name before development-mode prefixing |
| `max_concurrent_runs` | `1` | Prevents overlapping scheduled source runs |
| `timeout_seconds` | `5520` | Covers two 2700-second task attempts, the retry interval, and job overhead |
| `trigger.periodic` | one day | Daily trigger; paused in `dev` |
| `health.rules` | `RUN_DURATION_SECONDS > ${var.job_duration_warning_seconds}` | Native slow-run signal; default 900 seconds |
| `email_notifications.on_failure` | `${var.notification_emails}` | Approved internal dbt-failure recipients |
| `notification_settings` | mute skipped; alert canceled | Cancellation can interrupt artifact production and is material |

The source has one task, `dbt_nyc_taxi`:

```yaml
- task_key: dbt_nyc_taxi
  environment_key: default
  dbt_task:
    project_directory: ../
    warehouse_id: ${var.warehouse_id}
    catalog: ${var.catalog}
    schema: ${var.schema}
    commands:
      - >-
        dbt --log-format-file json
        build
        --target-path /Volumes/${var.catalog}/${resources.schemas.dbt_observability.name}/${resources.volumes.dbt_artifact_staging.name}/workspace_id={{workspace.id}}/job_id={{job.id}}/job_run_id={{job.run_id}}/repair_count={{job.repair_count}}/task_run_id={{task.run_id}}/execution_count={{task.execution_count}}/target
        --select +nyc_taxi_trips
        --quiet --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'
  timeout_seconds: 2700
  max_retries: 1
  min_retry_interval_millis: 60000
  retry_on_timeout: true
```

`dbt build` loads the selected seed, materializes the model, and runs attached
tests in one invocation. `--target-path` directs dbt's `manifest.json` and
`run_results.json` into a staging leaf unique to the actual task attempt. The
leaf contains the complete identity:

```text
workspace_id / job_id / job_run_id / repair_count /
task_run_id / execution_count
```

Task-level failure notification uses `alert_on_last_attempt: true`, so the first
failed attempt does not notify while a retry remains. The source contains no
collector task; its terminal state is the dbt result.

## Collector job: `dbt_observability_collector_job`

The deployed job name is `nyc_taxi_dbt_observability_collector`.

| Field | Committed value | Meaning |
|-------|-----------------|---------|
| `max_concurrent_runs` | `1` | Prevents overlapping collection sweeps |
| `timeout_seconds` | `1800` | Covers two 840-second task attempts, the retry interval, and job overhead |
| `schedule.quartz_cron_expression` | `0 0/15 * * * ?` | Starts a sweep every 15 minutes |
| `schedule.timezone_id` | `UTC` | Stable cross-region cadence |
| base `schedule.pause_status` | `PAUSED` | Safe by default; production target explicitly unpauses it |
| `health.rules` | `RUN_DURATION_SECONDS > 600` | Native slow-sweep signal |
| `email_notifications.on_failure` | `${var.notification_emails}` | Approved internal capture/cleanup recipients |
| `notification_settings` | mute skipped; alert canceled | Cancellation can interrupt reconciliation and is material |

### `collect_completed_dbt_artifacts`

```yaml
- task_key: collect_completed_dbt_artifacts
  environment_key: collector
  notebook_task:
    notebook_path: ../src/observability/collect_dbt_artifacts.py
    source: WORKSPACE
    base_parameters:
      source_job_id: ${resources.jobs.nyc_taxi_dbt_job.id}
      source_task_key: dbt_nyc_taxi
      lookback_days: "59"
      max_task_runs_per_sweep: "100"
      observability_catalog: ${var.catalog}
      observability_schema: ${resources.schemas.dbt_observability.name}
      observability_volume: ${resources.volumes.dbt_artifacts.name}
      observability_staging_volume: ${resources.volumes.dbt_artifact_staging.name}
  timeout_seconds: 840
  max_retries: 1
  min_retry_interval_millis: 60000
  retry_on_timeout: true
```

`workspace_id` is deliberately absent from the parameters. The collector gets
the authoritative value from `WorkspaceClient.get_workspace_id()`.

Each sweep lists completed source runs, reconciles matching staging leaves, and
processes at most 100 incomplete attempts from the 59-day lookback. Never-seen
attempts precede least-recently-attempted retries. A failure does not stop the
batch; the collector fails once after processing if captures failed or work was
deferred.

## Full AttemptKey and idempotency

The durable identity is:

```text
(workspace_id, job_id, job_run_id, repair_count, task_run_id, execution_count)
```

All six fields participate in registry/fact merge keys and storage paths. This
prevents retries, repairs, or additional executions from overwriting one
another. Re-running the collector reconciles the same attempt instead of adding
duplicates.

## Staging-to-evidence capture

For each completed attempt, the collector:

1. locates the full AttemptKey staging leaf;
2. reads exactly `target/manifest.json` and `target/run_results.json` through the
   governed POSIX-style `/Volumes/...` path;
3. creates a deterministic tar with fixed member order, names, modes,
   timestamps, and ownership metadata;
4. validates size, paths, schemas, invocation IDs, and allowlisted fields;
5. writes the canonical tar without overwrite beneath a SHA-256 path in the
   evidence Volume;
6. verifies the stored hash and merges invocation/node facts;
7. marks terminal capture only when the archive and expected facts reconcile;
   and
8. reconciles and deletes the staging leaf separately.

The tar contains only:

```text
target/manifest.json
target/run_results.json
```

Compiled SQL, dbt arguments, free-form messages, adapter responses, and logs are
not added to normalized facts. The selected JSON can still contain sensitive
metadata, so both staging and evidence remain restricted.

Databricks Volumes do not support direct append or non-sequential random writes.
This implementation uses sequential reads of completed JSON and sequential
writes of complete evidence objects only. It has no external or Azure-native
storage dependency.

## Capture and cleanup states

| `capture_status` | Terminal | Behavior |
|------------------|----------|----------|
| `COMPLETE` | yes | Canonical archive and all expected normalized facts reconcile |
| `QUARANTINED` | yes | Rejected artifact pair is durably stored below `quarantine/` with an allowlisted code |
| `NOT_PRODUCED` | yes | Completed source attempt did not produce the required artifact pair |
| `RETRYABLE_ERROR` | no | Transient staging/capture problem is retried |
| `UPLOAD_FAILED` | no | Evidence persistence or integrity verification is retried |

Staging cleanup has its own columns:

| Column | Values or meaning |
|--------|-------------------|
| `staging_cleanup_status` | `PENDING` or `DELETED` |
| `staging_cleanup_error_code` | Allowlisted deletion failure, otherwise null |
| `staging_cleanup_updated_at` | Last cleanup state transition |
| `staging_deleted_at` | Successful deletion time, otherwise null |

Terminal evidence is never downgraded merely because staging deletion failed.
A later sweep reconciles a `PENDING` leaf and retries deletion without rewriting
the canonical archive or duplicating normalized facts. Retryable capture states
retain staging for another attempt.

There is no default cleanup policy that deletes `COMPLETE` or `QUARANTINED`
evidence.

## Production identity boundary

| Identity | Job or operation | Required access |
|----------|------------------|-----------------|
| deployer | Bundle deployment | Manage resources and grants |
| dbt runner | `nyc_taxi_dbt_job` | SQL warehouse and target dbt objects; `READ VOLUME` and `WRITE VOLUME` only on staging |
| collector | `dbt_observability_collector_job` | `CAN_VIEW` source job; `READ VOLUME` and `WRITE VOLUME` on staging and evidence; evidence table privileges |

The dbt runner can read and write its short-lived target directory in staging,
but cannot access collector-only evidence or observability base tables. The
collector's staging write permission exists for reconciled deletion.

Routine operators receive `SELECT` only on sanitized views. They do not need
either Volume or the three restricted base tables.

## Integrity and retention boundary

The canonical archive is content-addressed, written without overwrite, and
verified against the registry hash. That makes unexpected change detectable at
the application layer. A managed Unity Catalog Volume is not WORM storage and a
sufficiently privileged identity can still mutate it. Regulated write-once
retention requires a separate approved control.

## Serverless environments

| Environment | Job | Exact dependencies |
|-------------|-----|--------------------|
| `default` | source | `dbt-core==1.11.11`, `dbt-databricks==1.12.2` |
| `collector` | collector | `databricks-sdk==0.117.0` |

Both use serverless environment version `"4"`. dbt anonymous usage statistics
are disabled in `dbt_project.yml`.

## Unity Catalog objects

```text
<catalog>.<observability_schema>_<target>
├── <observability_staging_volume>    # MANAGED, short-lived attempt leaves
└── <observability_volume>            # MANAGED, canonical evidence
```

On first collection the notebook creates:

- restricted tables `dbt_artifact_registry`, `dbt_invocations`, and
  `dbt_node_results`; and
- curated views `dbt_run_health`, `dbt_node_health`,
  `lakeflow_job_run_health`, `lakeflow_dbt_task_run_health`, and
  `dbt_job_health`.

The two native views are independently scoped to the configured workspace and
source job; the task view also filters the configured task key.
`dbt_job_health` starts from native job runs, joins task history by
`(workspace_id, job_id, job_run_id)`, and joins dbt evidence to the exact native
`task_run_id`. A terminal native run without registry evidence therefore
remains visible with `evidence_status = 'MISSING'`. Full AttemptKey columns
remain on the dbt evidence side so repairs and executions stay distinct without
cross-joining retries.

## dbt `--target` versus `--target-path`

The command omits dbt profile selector `--target`. Databricks generates a
single profile target from `warehouse_id`, `catalog`, and `schema`; local target
name `dev` does not exist in that generated profile.

The command does include `--target-path`, which only changes where dbt writes
JSON artifacts and compiled output. It does not select a connection target. See
[How dbt connects to Databricks](../explanation/how-dbt-connects.md).

## Related

- Runbook: [Observe dbt jobs](../how-to/observe-dbt-jobs.md)
- [Configuration values](configuration-values.md)
- [Bundle configuration](bundle-config.md)
