---
icon: lucide/badge-check
---

# Verify a production deployment

Prove that one protected deployment used the intended identities, captured its
exact dbt attempt, exposed sanitized facts, and remained idempotent when the
collector swept that attempt twice.

This verifies the repository's functional contract. AWS Free Edition is not a
regulated production environment and this procedure is not a compliance
certification.

## Prerequisites

You need:

- a successful protected `Deploy bundle (prod)` workflow run;
- GitHub CLI access, `jq`, and standard `grep`;
- a read-only Databricks OAuth U2M profile that can inspect the two jobs, their
  runs, and the deployed-directory ACL; and
- an approved, time-bounded verifier role with `USE CATALOG`, `USE SCHEMA`, and
  `SELECT` on `dbt_artifact_registry`, `dbt_invocations`, and
  `dbt_node_results`; and
- an owner, `MANAGE` principal, or administrator to inspect effective Unity
  Catalog grants in step 8.

Routine operators intentionally have only sanitized-view access and cannot run
the base-table checks in this guide. Grant privileged verification access only
for the approved review window, record it, and revoke it afterward. Registry
metadata such as archive locations remains restricted even when raw artifacts
are not selected.

An authorized Unity Catalog owner can establish the narrow verifier role:

```sql
GRANT USE CATALOG ON CATALOG `<catalog>` TO `<verifier-group>`;
GRANT USE SCHEMA
ON SCHEMA `<catalog>`.`<observability-schema>` TO `<verifier-group>`;
GRANT SELECT
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_artifact_registry`
TO `<verifier-group>`;
GRANT SELECT
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_invocations`
TO `<verifier-group>`;
GRANT SELECT
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_node_results`
TO `<verifier-group>`;
GRANT SELECT
ON VIEW `<catalog>`.`<observability-schema>`.`dbt_run_health`
TO `<verifier-group>`;
GRANT SELECT
ON VIEW `<catalog>`.`<observability-schema>`.`dbt_node_health`
TO `<verifier-group>`;
```

Do not start another production job or mutate bundle state through the human
profile. The protected workflow already created the acceptance source run and
two collector sweeps.

## 1. Record the workflow's exact run IDs

List successful workflow runs for the exact reviewed commit, then choose the
approved run ID:

```bash
export APPROVED_SHA="<full-reviewed-main-commit-sha>"
gh run list \
  --workflow deploy.yml \
  --commit "$APPROVED_SHA" \
  --status success \
  --json databaseId,headSha,url

export DEPLOY_RUN_ID="<approved-workflow-run-id-from-the-list>"
run_metadata="$(
  gh run view "$DEPLOY_RUN_ID" \
    --json headSha,conclusion,url
)"
jq -e --arg sha "$APPROVED_SHA" \
  '.headSha == $sha and .conclusion == "success"' \
  <<< "$run_metadata" >/dev/null
gh run view "$DEPLOY_RUN_ID" --exit-status
gh run view "$DEPLOY_RUN_ID" --log | grep 'ACCEPTANCE_RUN_IDS'
```

Record the four values from the single `ACCEPTANCE_RUN_IDS` line:

```text
source_parent, source_task, collector_1, collector_2
```

The source task ID is the `dbt_nyc_taxi` task run, not the parent run. Do not
substitute a newer scheduled or manually launched run.

## 2. Verify both job identities

Resolve each job by exact production name and reject zero or multiple matches:

```bash
source_job_id="$(
  databricks jobs list \
    --name nyc_taxi_dbt_job \
    --profile bricks-demo \
    --output json |
    jq -er 'map(select(.settings.name == "nyc_taxi_dbt_job")) |
      if length == 1 then .[0].job_id
      else error("expected exactly one production source job") end'
)"
collector_job_id="$(
  databricks jobs list \
    --name nyc_taxi_dbt_observability_collector \
    --profile bricks-demo \
    --output json |
    jq -er 'map(select(.settings.name == "nyc_taxi_dbt_observability_collector")) |
      if length == 1 then .[0].job_id
      else error("expected exactly one production collector job") end'
)"

databricks jobs get "$source_job_id" --profile bricks-demo --output json |
  jq '{name: .settings.name, run_as: .settings.run_as}'
databricks jobs get "$collector_job_id" --profile bricks-demo --output json |
  jq '{name: .settings.name, run_as: .settings.run_as,
       schedule: .settings.schedule}'
```

Confirm the source uses the approved runner application ID, the collector uses
the different collector application ID, and the production collector schedule
is `UNPAUSED`.

## 3. Verify the workflow-created runs

Replace the placeholders with the four IDs recorded in step 1:

```bash
databricks jobs get-run <source-parent-run-id> \
  --profile bricks-demo --output json |
  jq '{run_id, job_id, state,
       dbt_task: (.tasks[] | select(.task_key == "dbt_nyc_taxi") |
         {run_id, task_key, attempt_number, state})}'

databricks jobs get-run <collector-run-id-1> \
  --profile bricks-demo --output json |
  jq '{run_id, job_id, state}'
databricks jobs get-run <collector-run-id-2> \
  --profile bricks-demo --output json |
  jq '{run_id, job_id, state}'
```

Require `TERMINATED` / `SUCCESS` for the source parent and both collector runs.
Confirm the source response contains the recorded source task run ID.

## 4. Resolve the full AttemptKey

The Jobs API supplies the source parent and task run IDs, but the durable
registry is authoritative for the other AttemptKey fields. Resolve the exact
row with both recorded IDs:

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
  archive_path IS NOT NULL AS archive_path_recorded,
  archive_sha256,
  archive_bytes,
  file_count,
  invocation_id,
  parser_version
FROM `<catalog>`.`<observability-schema>`.`dbt_artifact_registry`
WHERE job_run_id = <source-parent-run-id>
  AND task_run_id = <source-task-run-id>;
```

Require exactly one row. Copy its six numeric key values; every remaining SQL
check must use all six:

```text
workspace_id, job_id, job_run_id, repair_count, task_run_id, execution_count
```

For a normal successful source attempt, require:

- `capture_status = 'COMPLETE'` and `capture_error_code IS NULL`;
- `staging_cleanup_status = 'DELETED'`;
- non-null archive path, SHA-256, and invocation ID;
- `file_count = 2`; and
- all six AttemptKey fields populated.

## 5. Verify the exact sanitized facts

Substitute the six values copied in step 4:

```sql
SELECT
  invocation_status,
  total_nodes,
  success_nodes,
  warning_nodes,
  failed_nodes,
  skipped_nodes,
  elapsed_seconds
FROM `<catalog>`.`<observability-schema>`.`dbt_run_health`
WHERE workspace_id = <workspace-id>
  AND job_id = <job-id>
  AND job_run_id = <job-run-id>
  AND repair_count = <repair-count>
  AND task_run_id = <task-run-id>
  AND execution_count = <execution-count>;

SELECT
  resource_type,
  node_name,
  status,
  execution_seconds
FROM `<catalog>`.`<observability-schema>`.`dbt_node_health`
WHERE workspace_id = <workspace-id>
  AND job_id = <job-id>
  AND job_run_id = <job-run-id>
  AND repair_count = <repair-count>
  AND task_run_id = <task-run-id>
  AND execution_count = <execution-count>
ORDER BY resource_type, node_name;
```

Require one invocation fact and the expected model, seed, and test nodes. The
views exclude raw SQL, free-form messages, and archive paths.

## 6. Prove idempotency for that AttemptKey

The protected workflow already ran the collector twice. Check the exact key in
both normalized tables and check node-key uniqueness:

```sql
SELECT
  (
    SELECT count(*)
    FROM `<catalog>`.`<observability-schema>`.`dbt_artifact_registry`
    WHERE workspace_id = <workspace-id>
      AND job_id = <job-id>
      AND job_run_id = <job-run-id>
      AND repair_count = <repair-count>
      AND task_run_id = <task-run-id>
      AND execution_count = <execution-count>
  ) AS registry_rows,
  (
    SELECT count(*)
    FROM `<catalog>`.`<observability-schema>`.`dbt_invocations`
    WHERE workspace_id = <workspace-id>
      AND job_id = <job-id>
      AND job_run_id = <job-run-id>
      AND repair_count = <repair-count>
      AND task_run_id = <task-run-id>
      AND execution_count = <execution-count>
  ) AS invocation_rows,
  (
    SELECT count(*)
    FROM `<catalog>`.`<observability-schema>`.`dbt_node_results`
    WHERE workspace_id = <workspace-id>
      AND job_id = <job-id>
      AND job_run_id = <job-run-id>
      AND repair_count = <repair-count>
      AND task_run_id = <task-run-id>
      AND execution_count = <execution-count>
  ) AS node_rows,
  (
    SELECT count(DISTINCT unique_id)
    FROM `<catalog>`.`<observability-schema>`.`dbt_node_results`
    WHERE workspace_id = <workspace-id>
      AND job_id = <job-id>
      AND job_run_id = <job-run-id>
      AND repair_count = <repair-count>
      AND task_run_id = <task-run-id>
      AND execution_count = <execution-count>
  ) AS distinct_node_rows;
```

Require `registry_rows = 1`, `invocation_rows = 1`, `node_rows > 0`, and
`node_rows = distinct_node_rows`.

## 7. Verify workspace-file access

Read the stable path from the approved deployer application-ID variable:

```bash
deployer="$(gh variable get DATABRICKS_CLIENT_ID)"
bundle_files="/Workspace/Users/${deployer}/.bundle/bricks_cli_dbt/prod/files"
object_id="$(
  databricks workspace get-status \
    "$bundle_files" \
    --profile bricks-demo \
    --output json |
    jq -er '.object_id'
)"
databricks permissions get \
  directories "$object_id" \
  --profile bricks-demo \
  --output json
```

Confirm runner `CAN_READ`, collector `CAN_RUN`, no runtime edit/manage grant,
and no obsolete direct runtime principal.

## 8. Verify the governed data boundary

Inspect the bundle-created Volume grants:

```sql
SHOW GRANTS `<runner-application-id>`
ON VOLUME `<catalog>`.`<observability-schema>`.`dbt_artifacts_staging`;

SHOW GRANTS `<collector-application-id>`
ON VOLUME `<catalog>`.`<observability-schema>`.`dbt_artifacts_staging`;

SHOW GRANTS `<collector-application-id>`
ON VOLUME `<catalog>`.`<observability-schema>`.`dbt_artifacts`;

SHOW GRANTS `<runner-application-id>`
ON VOLUME `<catalog>`.`<observability-schema>`.`dbt_artifacts`;
```

Require runner and collector read/write access on staging, collector read/write
access on evidence, and no runner evidence-Volume privilege.

Verify that the runner has no direct or inherited access to the three
restricted base tables:

```sql
SHOW GRANTS `<runner-application-id>`
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_artifact_registry`;

SHOW GRANTS `<runner-application-id>`
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_invocations`;

SHOW GRANTS `<runner-application-id>`
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_node_results`;
```

Fail verification if group or parent-object inheritance gives the runner
`READ VOLUME`, `WRITE VOLUME`, `SELECT`, or `MODIFY` across the canonical
evidence boundary.

## 9. Check optional Lakeflow enrichment

When system-table access is approved, query the three optional views. System
tables can lag, so missing or stale optional rows do not invalidate canonical
artifact capture. Check the collector task output for
`SYSTEM_LAKEFLOW_VIEW_UNAVAILABLE` before treating their absence as a dbt
failure.

## 10. Close privileged verification access

Revoke any temporary base-table `SELECT` grants issued to the verifier and
confirm the routine operator boundary from
[Permissions](../reference/permissions.md). Preserve the query results required
by the approved change record, but do not export raw artifacts or signed links.

```sql
REVOKE SELECT
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_artifact_registry`
FROM `<verifier-group>`;
REVOKE SELECT
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_invocations`
FROM `<verifier-group>`;
REVOKE SELECT
ON TABLE `<catalog>`.`<observability-schema>`.`dbt_node_results`
FROM `<verifier-group>`;
REVOKE SELECT
ON VIEW `<catalog>`.`<observability-schema>`.`dbt_run_health`
FROM `<verifier-group>`;
REVOKE SELECT
ON VIEW `<catalog>`.`<observability-schema>`.`dbt_node_health`
FROM `<verifier-group>`;
```

Revoke temporary `USE SCHEMA` or `USE CATALOG` only when those privileges were
created solely for this review; do not remove an approved pre-existing grant.

## Success criteria

Verification passes when:

- the exact workflow-created source and two collector runs succeeded;
- jobs use distinct intended `run_as` service principals;
- the exact six-field AttemptKey is `COMPLETE` with two archived files and
  deleted staging;
- one matching invocation and a unique set of node facts exist after both
  sweeps; and
- the deployed-directory and governed-data ACLs preserve least privilege.

## Recovery

| Failure | First recovery action |
|---|---|
| Project or notebook permission error | Follow [Repair production runtime file access](grant-production-runtime-access.md) |
| Source warehouse/catalog error | Repair external runner prerequisites |
| Collector cannot view source runs | Repair collector `CAN_VIEW` on the source job |
| `UPLOAD_FAILED` | Check evidence Volume privileges and existing digest path |
| `RETRYABLE_ERROR` | Preserve staging and let a later sweep retry after repair |
| Cleanup `PENDING` | Fix staging write/delete access and let a later sweep retry |
| Only Lakeflow views missing | Check optional system-table grants and ingestion lag |
| Free Edition compute unavailable | Wait for fair-use availability; do not weaken controls |

Use [Observability operations](observe-dbt-jobs.md) to route deeper
investigation.
