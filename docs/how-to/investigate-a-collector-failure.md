---
icon: lucide/package-x
---

# Investigate a collector failure

Use this guide when `nyc_taxi_dbt_observability_collector` fails. A collector
failure does not change the upstream dbt result; it means capture, validation,
upload, registry reconciliation, or staging cleanup needs attention.

## 1. Read the first stable error code

Open the collector task output in Databricks, or retrieve the parent metadata
and task output separately:

```bash
collector_run="$(
  databricks jobs get-run <collector-parent-run-id> \
    --profile <profile> \
    --output json
)"
collector_task_run_id="$(
  jq -er \
    '.tasks[] | select(.task_key == "collect_completed_dbt_artifacts") | .run_id' \
    <<< "$collector_run"
)"

jq '{job_id, run_id, state,
     collector_task: (.tasks[] |
       select(.task_key == "collect_completed_dbt_artifacts") |
       {run_id, attempt_number, state})}' <<< "$collector_run"
databricks jobs get-run-output "$collector_task_run_id" \
  --profile <profile> \
  --output json |
  jq '{error, metadata: {
    job_id: .metadata.job_id,
    run_id: .metadata.run_id,
    task_key: .metadata.task_key,
    state: .metadata.state
  }}'
```

`jobs get-run` supplies metadata; `jobs get-run-output` supplies the selected
task's bounded error field. The projection excludes notebook output, logs,
signed links, and the raw traceback. Current collector failures include stable,
uppercase codes in the raised error summary. Older deployments or a truncated
platform response can show only a generic `RuntimeError`; in that case, read
the task log in the Databricks UI and query the registry error columns in step
2. Look up each observed code in [Error codes](../reference/error-codes.md).

`SYSTEM_LAKEFLOW_VIEW_UNAVAILABLE` is different: it says optional system-table
views could not be refreshed. Baseline artifact capture and the two dbt views
can still be healthy.

## 2. Query the registry state through the curated view

```sql
SELECT
  job_run_id,
  repair_count,
  task_run_id,
  execution_count,
  capture_status,
  capture_error_code,
  staging_cleanup_status,
  staging_cleanup_error_code,
  captured_at
FROM `<catalog>`.`<observability-schema>`.`dbt_run_health`
WHERE capture_status <> 'COMPLETE'
   OR staging_cleanup_status <> 'DELETED'
ORDER BY captured_at DESC;
```

Interpret capture and cleanup independently:

- `RETRYABLE_ERROR` or `UPLOAD_FAILED`: remove the transient cause and let a
  later sweep retry the attempt;
- `QUARANTINED`: preserve the quarantine archive and investigate the validation
  code under your evidence-handling procedure;
- `NOT_PRODUCED`: the absence has been recorded as a terminal fact; and
- cleanup `PENDING`: the capture result is durable but staging deletion still
  needs reconciliation.

## 3. Check identity and grants

Confirm that the collector run uses the configured collector service principal.
It needs:

- `CAN_VIEW` on the source job;
- `CAN_RUN` on the deployed collector files;
- use/create/select/modify rights in the dedicated observability schema; and
- read/write access to both staging and evidence Volumes.

It does not need permission to edit deployed files or manage the source job.

## 4. Check discovery boundaries

The collector examines at most 100 completed task runs per sweep and looks back
at most 59 days. A large backlog can require multiple successful sweeps. It also
rejects unsafe identifiers and bounded-runtime parameters instead of widening
its scope.

## 5. Reconcile safely

Fix the grant, transient storage condition, deployed-file ACL, or parameter that
caused the failure. Then wait for the next 15-minute production schedule. Do not
copy the deployer secret into a local profile or mutate the production bundle
through a human U2M session merely to force a sweep.

The job has `max_retries: 0` so its first failure remains observable. A later
sweep skips terminal attempts, retries non-terminal attempts, and independently
retries pending cleanup.

Verify that the new collector run succeeded and that the affected row reached
the expected capture and cleanup states. Do not delete a registry row to force a
retry.
