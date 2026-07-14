---
icon: lucide/archive
---

# Artifact collector job

`resources/dbt_observability_collector.job.yml` defines an independent
post-run collector. It reconciles completed source attempts into governed
archives and sanitized Delta facts.

## Resource identity

| Field | Value |
|-------|-------|
| Bundle resource key | `dbt_observability_collector_job` |
| Base job name | `nyc_taxi_dbt_observability_collector` |
| Task key | `collect_completed_dbt_artifacts` |
| Notebook | `src/observability/collect_dbt_artifacts.py` |
| Environment key | `collector` |
| Maximum concurrent runs | `1` |
| Job timeout | `900` seconds |
| Task timeout | `840` seconds |
| Task retries | `0` |
| Production `run_as` | `${var.prod_collector_service_principal_name}` |

No in-run retry is intentional: the first failed sweep remains visible as a
failed Lakeflow run. The next scheduled or manual sweep performs reconciliation.

## Schedule

```text
quartz_cron_expression = 0 0/15 * * * ?
timezone_id             = UTC
base pause_status       = PAUSED
production override     = UNPAUSED
```

The schedule starts one sweep every 15 minutes in production. Development keeps
it paused for manual validation.

CLI `1.7.0` production-mode presets also resolve job queueing as enabled and
`edit_mode` as `UI_LOCKED`.

## Notebook inputs

| Parameter | Committed value | Accepted contract |
|-----------|-----------------|-------------------|
| `source_job_id` | Resolved source job ID | positive integer |
| `source_task_key` | `dbt_nyc_taxi` | safe identifier, at most 128 characters |
| `lookback_days` | `59` | 1–59 |
| `max_task_runs_per_sweep` | `100` | 1–100 |
| `observability_catalog` | `${var.catalog}` | safe identifier |
| `observability_schema` | Resolved target schema | safe identifier |
| `observability_volume` | Resolved evidence Volume | safe identifier |
| `observability_staging_volume` | Resolved staging Volume | safe identifier |

`workspace_id` is taken from `WorkspaceClient.get_workspace_id()` and cannot be
overridden by a notebook parameter.

## Discovery and batching

The collector:

1. lists only completed runs of the configured source job within 59 days;
2. selects only the configured task and verifies its `--target-path`
   instrumentation;
3. correlates each staged leaf's parent and task run IDs to Jobs API history;
4. records an instrumented completed attempt with no staging as terminal
   `NOT_PRODUCED`;
5. processes never-seen attempts before retries;
6. orders retries by oldest `captured_at`; and
7. shares the 100-attempt capture budget across missing-staging gaps and staged
   incomplete attempts.

If more work remains, `deferred` is non-zero and the collector fails the sweep
so backlog is visible. Later sweeps drain the remaining attempts.

## Capture behavior

For each selected attempt the collector:

1. reads only `target/manifest.json` and `target/run_results.json`;
2. creates a deterministic gzip-compressed tar;
3. validates paths, limits, JSON structure, supported dbt schemas, invocation
   identity, and node statuses;
4. writes without overwrite to a SHA-256 content-addressed path;
5. verifies the remote hash;
6. merges invocation and node facts;
7. marks the registry terminal only after evidence reconciles; and
8. deletes staging separately after terminal capture.

See [Evidence layout](evidence-layout.md), [Capture states](capture-states.md),
and [Error codes](error-codes.md).

## Outputs

| Output | Guarantee |
|--------|-----------|
| Three restricted Delta tables | Created if absent on every sweep |
| `dbt_run_health` | Always refreshed after table creation |
| `dbt_node_health` | Always refreshed after table creation |
| `lakeflow_job_run_health` | Best effort; requires system-table access |
| `lakeflow_dbt_task_run_health` | Best effort; requires system-table access |
| `dbt_job_health` | Best effort; requires both Lakeflow views |
| Evidence archive or quarantine object | Created for staged content before terminal registry status |

Failure to refresh the three Lakeflow-backed views does not fail artifact
capture. The notebook prints `SYSTEM_LAKEFLOW_VIEW_UNAVAILABLE`.

## Health and notifications

| Signal | Condition | Recipients |
|--------|-----------|------------|
| Failure | Capture, cleanup, discovery, or deferred backlog | `${var.notification_emails}` |
| Duration warning | `RUN_DURATION_SECONDS > 600` | `${var.notification_emails}` |
| Cancellation | Alert enabled | `${var.notification_emails}` |
| Skipped run | Alert muted | none |

Recipients default to `[]`.

## Runtime

```text
environment_version = 4
databricks-sdk       = 0.117.0
```

## Terminal output

A successful sweep prints counts for `discovered`, `discovery_gaps`,
`gaps_recorded`, `terminal_skipped`, `attempted`, `captured`, `cleaned`,
`failed`, and `deferred`. It raises a runtime error with bounded stable codes
when `failed > 0` or `deferred > 0`.

## Example

```bash
databricks bundle run dbt_observability_collector_job \
  --target dev --profile bricks-demo
```
