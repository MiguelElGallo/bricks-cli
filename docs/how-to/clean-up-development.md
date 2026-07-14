---
icon: lucide/trash-2
---

# Clean up a development deployment

Use this guide to remove one disposable `dev` bundle deployment and its
dedicated dbt data schema without deleting unresolved staging work.

!!! danger "Never use this guide for production"
    The `prod` observability schema and Volumes have `prevent_destroy` controls
    because their contents can be operational evidence. Production retention
    and decommissioning require a separate approved process.

## Re-establish the deployment inputs

Use the same CLI profile and exact `BUNDLE_VAR_*` values that created the
development deployment:

```bash
export DATABRICKS_PROFILE="<your-profile>"
export BUNDLE_VAR_warehouse_id="<same-warehouse-id>"
export BUNDLE_VAR_catalog="<same-catalog>"
export BUNDLE_VAR_schema="<dedicated-development-schema>"
export BUNDLE_VAR_observability_schema="<same-observability-base-name>"
export BUNDLE_VAR_observability_staging_volume="<same-staging-volume-name>"
export BUNDLE_VAR_observability_volume="<same-evidence-volume-name>"
```

Show the deployed target before deleting anything:

```bash
databricks bundle summary \
  --target dev \
  --profile "$DATABRICKS_PROFILE"
```

Confirm that the summary names the intended development source job, collector
job, observability schema, and Volumes. Record the exact resolved observability
schema name.

## Reconcile incomplete staging

Run one collector sweep:

```bash
databricks bundle run dbt_observability_collector_job \
  --target dev \
  --profile "$DATABRICKS_PROFILE"
```

The sweep should succeed. In a Databricks SQL editor, verify that no retryable
capture or pending cleanup remains:

```sql
SELECT count(*) AS unresolved
FROM `<catalog>`.`<resolved-observability-schema>`.`dbt_artifact_registry`
WHERE capture_status IN ('RETRYABLE_ERROR', 'UPLOAD_FAILED')
   OR staging_cleanup_status = 'PENDING';
```

Continue only when the result is `0`. If it is nonzero, investigate the
collector failure and rerun the sweep instead of deleting staging.

## Remove runtime-created views and tables

Run this target-scoped SQL after replacing the catalog and schema placeholders:

```sql
DROP VIEW IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`dbt_job_health`;
DROP VIEW IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`lakeflow_dbt_task_run_health`;
DROP VIEW IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`lakeflow_job_run_health`;
DROP VIEW IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`dbt_node_health`;
DROP VIEW IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`dbt_run_health`;

DROP TABLE IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`dbt_node_results`;
DROP TABLE IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`dbt_invocations`;
DROP TABLE IF EXISTS `<catalog>`.`<resolved-observability-schema>`.`dbt_artifact_registry`;
```

All statements should succeed. The bundle can now remove the schema and its
managed Volumes without colliding with collector-created relations.

## Destroy the development bundle

Run:

```bash
databricks bundle destroy \
  --target dev \
  --profile "$DATABRICKS_PROFILE" \
  --auto-approve
```

The command should report a completed destroy. The development jobs,
observability schema, and both Volumes should disappear from the workspace.

## Remove the dedicated dbt schema

Remove only the relations known to belong to this disposable deployment:

```sql
DROP TABLE IF EXISTS `<catalog>`.`<dedicated-development-schema>`.`long_trips`;
DROP TABLE IF EXISTS `<catalog>`.`<dedicated-development-schema>`.`nyc_taxi_trips`;
DROP TABLE IF EXISTS `<catalog>`.`<dedicated-development-schema>`.`nyc_taxi_trips_seed`;
DROP SCHEMA IF EXISTS `<catalog>`.`<dedicated-development-schema>`;
```

Omit `long_trips` if that model was never created. Do not use `CASCADE`: an
unexpected relation should stop cleanup for review.

List the jobs and schemas in the workspace to verify that the target-scoped
resources are gone. The repository and local OAuth profile are not affected.
