---
icon: lucide/play-circle
---

# Source dbt job

`resources/nyc_taxi.job.yml` defines the serverless source job. Its terminal
result is the dbt result; artifact collection runs in a separate job.

## Resource identity

| Field | Value |
|-------|-------|
| Bundle resource key | `nyc_taxi_dbt_job` |
| Base job name | `nyc_taxi_dbt_job` |
| Task key | `dbt_nyc_taxi` |
| Environment key | `default` |
| Maximum concurrent runs | `1` |
| Job timeout | `5520` seconds |
| Trigger | periodic, every `1 DAYS` |
| Production `run_as` | `${var.prod_run_as_service_principal_name}` |

Development mode prefixes the name and pauses the trigger. Production uses the
base name and active trigger. CLI `1.7.0` production-mode presets also resolve
job queueing as enabled and `edit_mode` as `UI_LOCKED`.

## Tags

| Key | Value |
|-----|-------|
| `environment` | `${bundle.target}` |
| `workload` | `dbt` |
| `dbt_project` | `${bundle.name}` |
| `criticality` | `reference` |
| `observability` | `databricks_native` |

## dbt task

```text
project_directory = ../
warehouse_id      = ${var.warehouse_id}
catalog           = ${var.catalog}
schema            = ${var.schema}
```

The single command is:

```bash
dbt --log-format-file json build \
  --target-path /Volumes/${var.catalog}/${resources.schemas.dbt_observability.name}/${resources.volumes.dbt_artifact_staging.name}/workspace_id={{workspace.id}}/job_id={{job.id}}/job_run_id={{job.run_id}}/repair_count={{job.repair_count}}/task_run_id={{task.run_id}}/execution_count={{task.execution_count}}/target \
  --select +nyc_taxi_trips +weather_station_summary \
  --quiet --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'
```

The two terminal selectors include both complete ancestor graphs and their
attached tests in one dbt invocation. For the current project, that resolved to
15 nodes during validation: two seeds, three models, and ten tests.
`--target-path` stages dbt JSON output under the exact task-attempt identity.
The command does not pass dbt `--target`; Databricks generates the connection
profile from the task's warehouse, catalog, and schema.

See the official [dbt task for jobs](https://docs.databricks.com/aws/en/jobs/dbt)
and [Lakeflow dynamic value references](https://docs.databricks.com/aws/en/jobs/dynamic-value-references).

## Retry and timeout

| Field | Value | Effect |
|-------|-------|--------|
| Task timeout | `2700` seconds | One attempt can run for 45 minutes |
| `max_retries` | `1` | At most two task attempts |
| Retry interval | `60000` milliseconds | One minute between attempts |
| `retry_on_timeout` | `true` | A timed-out first attempt is retryable |
| `alert_on_last_attempt` | `true` | Task failure email waits until retries are exhausted |

The job timeout covers two task timeouts, the retry interval, and orchestration
headroom.

## Health and notifications

| Signal | Condition | Recipients |
|--------|-----------|------------|
| Failure | Job or final task attempt fails | `${var.notification_emails}` |
| Duration warning | `RUN_DURATION_SECONDS > ${var.job_duration_warning_seconds}` | `${var.notification_emails}` |
| Cancellation | Alert enabled | `${var.notification_emails}` |
| Skipped run | Alert muted | none |

`notification_emails` defaults to `[]`, so the committed project has no email
recipient and no outbound notification until an approved value is supplied.

## Runtime

```text
environment_version = 4
dbt-core             = 1.11.11
dbt-databricks       = 1.12.2
```

The source identity must be able to read deployed project files, use the SQL
warehouse, build in the dbt schema, and read/write only the staging Volume. See
[Permissions](permissions.md).

## Outputs

| Output | Location |
|--------|----------|
| Taxi seed relation | `${var.catalog}.${var.schema}.nyc_taxi_trips_seed` |
| Taxi model relation | `${var.catalog}.${var.schema}.nyc_taxi_trips` |
| Weather seed relation | `${var.catalog}.${var.schema}.weather_daily_seed` |
| Weather daily model | `${var.catalog}.${var.schema}.weather_daily_observations` |
| Weather summary model | `${var.catalog}.${var.schema}.weather_station_summary` |
| dbt manifest | Attempt staging leaf `target/manifest.json`, when dbt produces it |
| dbt run results | Attempt staging leaf `target/run_results.json`, when dbt produces it |
| Native job state | Lakeflow Jobs run history |

The source job has no collector task. Capture failure cannot change its already
terminal result.

## Example

```bash
databricks bundle run nyc_taxi_dbt_job --target dev --profile bricks-demo
```
