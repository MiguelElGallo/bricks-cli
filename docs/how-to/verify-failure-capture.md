---
icon: lucide/shield-alert
---

# Verify missing-artifact capture

Create one controlled development attempt that never writes to the configured
staging path, prove it becomes `NOT_PRODUCED`, and prove another collector sweep
does not duplicate the terminal fact.

!!! danger "Disposable development target only"

    Never manufacture missing evidence in production and never delete an
    artifact to create this condition. Use a separately named development dbt
    schema and an approved disposable development deployment.

## Before you begin

You need:

- a deployed `dev` target with its required bundle variables loaded;
- a U2M profile that can run both development jobs;
- `jq`; and
- SQL access to the development observability schema.

Ensure no unrelated development run is active. The collector processes a
bounded workspace backlog, so an isolated development deployment makes the
expected first-failure/second-success sequence unambiguous.

## 1. Resolve the development jobs

```bash
summary="$(
  databricks bundle summary \
    --target dev \
    --profile <profile> \
    --output json
)"
source_job_id="$(
  jq -er '.resources.jobs.nyc_taxi_dbt_job.id' <<< "$summary"
)"
collector_job_id="$(
  jq -er '.resources.jobs.dbt_observability_collector_job.id' <<< "$summary"
)"
```

Stop if either lookup fails.

## 2. Create a controlled no-staging attempt

Override the single dbt task for this run with an intentionally invalid dbt
option. The command fails before project execution and deliberately omits the
instrumented `--target-path`; it does not delete or alter an artifact.

```bash
request="$(
  jq -cn \
    --argjson job_id "$source_job_id" \
    '{
      job_id: $job_id,
      dbt_commands: ["dbt --definitely-invalid-option"]
    }'
)"
source_run="$(
  databricks jobs run-now \
    --json "$request" \
    --timeout 10m \
    --profile <profile> \
    --output json
)"

jq -e '
  .state.life_cycle_state == "TERMINATED" and
  .state.result_state == "FAILED"
' <<< "$source_run" >/dev/null

job_run_id="$(jq -er '.run_id' <<< "$source_run")"
task_run_id="$(
  jq -er '.tasks[] | select(.task_key == "dbt_nyc_taxi") | .run_id' \
    <<< "$source_run"
)"
printf 'Controlled parent=%s task=%s\n' "$job_run_id" "$task_run_id"
```

The Databricks CLI waits for terminal lifecycle state but does not itself fail
on a remote `FAILED` result, so the explicit `jq -e` assertion is required.

## 3. Run the first collector sweep

```bash
collector_run_1="$(
  databricks jobs run-now "$collector_job_id" \
    --timeout 20m \
    --profile <profile> \
    --output json
)"
jq -e '
  .state.life_cycle_state == "TERMINATED" and
  .state.result_state == "FAILED"
' <<< "$collector_run_1" >/dev/null
```

In an isolated deployment, this first sweep fails intentionally because it
records `STAGED_ARTIFACT_NOT_PRODUCED` rather than silently accepting the gap.

## 4. Resolve and verify the full AttemptKey

The Jobs API provides the parent and task run IDs. Resolve the complete key from
the durable registry row:

```sql
SELECT
  workspace_id,
  job_id,
  job_run_id,
  repair_count,
  task_run_id,
  execution_count,
  capture_status,
  capture_error_code,
  staging_cleanup_status
FROM `<catalog>`.`<observability-schema-dev>`.`dbt_artifact_registry`
WHERE job_run_id = <controlled-parent-run-id>
  AND task_run_id = <controlled-task-run-id>;
```

Require exactly one row with:

```text
capture_status     = NOT_PRODUCED
capture_error_code = STAGED_ARTIFACT_NOT_PRODUCED
```

Copy all six numeric AttemptKey values. Cleanup can be `DELETED` even when no
leaf remained; capture and cleanup are separate state machines.

## 5. Run the second sweep

```bash
collector_run_2="$(
  databricks jobs run-now "$collector_job_id" \
    --timeout 20m \
    --profile <profile> \
    --output json
)"
jq -e '
  .state.life_cycle_state == "TERMINATED" and
  .state.result_state == "SUCCESS"
' <<< "$collector_run_2" >/dev/null
```

`NOT_PRODUCED` is terminal, so the collector skips the registered AttemptKey.
If an unrelated backlog makes the whole sweep fail, continue with the exact-key
SQL assertion rather than treating that separate failure as a duplicate.

## 6. Prove exactly-once terminal capture

Substitute the six values copied in step 4:

```sql
SELECT
  count(*) AS registry_rows,
  min(capture_status) AS capture_status,
  min(capture_error_code) AS capture_error_code
FROM `<catalog>`.`<observability-schema-dev>`.`dbt_artifact_registry`
WHERE workspace_id = <workspace-id>
  AND job_id = <job-id>
  AND job_run_id = <job-run-id>
  AND repair_count = <repair-count>
  AND task_run_id = <task-run-id>
  AND execution_count = <execution-count>;
```

Require one row, `NOT_PRODUCED`, and
`STAGED_ARTIFACT_NOT_PRODUCED`. A later repair or retry has a different
AttemptKey and must not overwrite this row.

## 7. Finish the test

Run an ordinary healthy development source job and collector sweep, then verify
a new `COMPLETE` / `DELETED` attempt. Follow
[Clean up a development deployment](clean-up-development.md) when the target was
disposable.
