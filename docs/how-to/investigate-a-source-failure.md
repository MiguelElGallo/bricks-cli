---
icon: lucide/circle-x
---

# Investigate a source failure

Use this guide when `nyc_taxi_dbt_job` fails. The source job reports the dbt
outcome; the collector reports whether the attempt's evidence was preserved.
Treat those as two separate questions.

## 1. Identify the exact attempt

Open the failed parent run in **Workflows > Jobs & Pipelines**, or retrieve its
metadata and the dbt task output separately:

```bash
parent_run="$(
  databricks jobs get-run <job-run-id> \
    --profile <profile> \
    --output json
)"
task_run_id="$(
  jq -er '.tasks[] | select(.task_key == "dbt_nyc_taxi") | .run_id' \
    <<< "$parent_run"
)"

jq '{job_id, run_id, state,
     dbt_task: (.tasks[] | select(.task_key == "dbt_nyc_taxi") |
       {run_id, attempt_number, state})}' <<< "$parent_run"
databricks jobs get-run-output "$task_run_id" \
  --profile <profile> \
  --output json |
  jq '{metadata: {
    job_id: .metadata.job_id,
    run_id: .metadata.run_id,
    task_key: .metadata.task_key,
    state: .metadata.state
  }}'
```

`jobs get-run` returns run metadata; `jobs get-run-output` returns the selected
task's output envelope. The strict projection deliberately excludes
`dbt_output`, artifact links, signed storage URLs, logs, and error traces. Use
the Databricks UI inside the approved access boundary when deeper log content is
authorized. Neither response supplies the full six-part AttemptKey. Record the
parent and task run IDs first:

```text
job_run_id, task_run_id
```

Do not identify an attempt by parent `job_run_id` alone: a retry or repair has a
different task run and execution count.

## 2. Classify the source failure

Inspect the dbt task output and the terminal `result_state`. Common categories
are:

- authentication or SQL warehouse access;
- Unity Catalog permissions;
- compilation or dependency errors;
- model, seed, or test failures;
- timeout or platform interruption; and
- no nodes selected, which is promoted to an error by this project.

Use the task log only within your approved Databricks boundary. Logs can include
more context than the sanitized observability views.

## 3. Check the independent capture outcome

After the collector's next sweep, resolve the durable row with both IDs:

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
  staging_cleanup_status
FROM `<catalog>`.`<observability-schema>`.`dbt_run_health`
WHERE job_run_id = <parent-run-id>
  AND task_run_id = <task-run-id>;
```

Require at most one row. When present, copy all six numeric identifiers from
that row and use the complete key for subsequent node and repair comparisons.

- `COMPLETE` means the manifest and run results were validated and archived,
  even when dbt failed.
- `NOT_PRODUCED` means that completed attempt produced no discoverable staging
  leaf.
- `QUARANTINED` means evidence existed but failed validation.
- no row may mean the collector has not swept the run yet, the run is outside
  the 59-day lookback, or collector discovery failed.

## 4. Inspect sanitized node facts

When capture is `COMPLETE`, query `dbt_node_health` with all six AttemptKey
fields. This can identify failed tests or models without exposing messages or
compiled SQL.

## 5. Repair the source job

Fix the dbt code, connection, warehouse, or grant that caused the source
failure. Validate locally or in the development target first, then use the Jobs
repair action when preserving the original parent run matters.

After repair, verify both the repaired source attempt and its separate collector
capture. Never rewrite the registry row for the failed attempt; the repaired
attempt has its own `repair_count`, `task_run_id`, and `execution_count`.

If capture rather than dbt is failing, switch to
[Investigate a collector failure](investigate-a-collector-failure.md).
