---
icon: lucide/trash-2
---

# Clean up the tutorial

We will remove the collector-created Delta objects first, then let the bundle
remove its development jobs, schema, and Volumes. Finally, we will remove the
two dbt relations from the dedicated tutorial schema.

!!! danger "Development tutorial only"
    Use these steps only for the `dev` target and the dedicated
    `dbt_nyc_taxi_tutorial` data schema. Production evidence has separate
    retention and decommissioning controls.

## Reconcile staging one last time

Run the collector again:

```bash
databricks bundle run dbt_observability_collector_job \
  --target dev \
  --profile bricks-demo
```

The no-new-work sweep should succeed. It must not create a second capture row
for the source attempt.

In the Databricks SQL editor, confirm that no retryable capture or staging
cleanup remains. Replace both placeholders with the values used earlier:

```sql
SELECT count(*) AS unresolved
FROM `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_artifact_registry`
WHERE capture_status IN ('RETRYABLE_ERROR', 'UPLOAD_FAILED')
   OR staging_cleanup_status = 'PENDING';
```

The result must be `0` before you continue.

## Remove the collector-created objects

The bundle owns the observability schema and Volumes, but the collector creates
its tables and views at runtime. Remove those runtime objects in the SQL editor:

```sql
DROP VIEW IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_job_health`;
DROP VIEW IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`lakeflow_dbt_task_run_health`;
DROP VIEW IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`lakeflow_job_run_health`;
DROP VIEW IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_node_health`;
DROP VIEW IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_run_health`;

DROP TABLE IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_node_results`;
DROP TABLE IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_invocations`;
DROP TABLE IF EXISTS `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_artifact_registry`;
```

Every statement should complete successfully. `IF EXISTS` also makes the
optional Lakeflow views safe to remove when system-table access was unavailable.

## Destroy the development bundle

Return to the same terminal, where the tutorial `BUNDLE_VAR_*` values are still
exported, and run:

```bash
databricks bundle destroy \
  --target dev \
  --profile bricks-demo \
  --auto-approve
```

The command should report a completed destroy. The development source job,
collector job, observability schema, and both managed Volumes are now gone.

## Remove the tutorial data

In the SQL editor, remove only the two known dbt relations and their dedicated
schema:

```sql
DROP TABLE IF EXISTS `<your-catalog>`.`dbt_nyc_taxi_tutorial`.`nyc_taxi_trips`;
DROP TABLE IF EXISTS `<your-catalog>`.`dbt_nyc_taxi_tutorial`.`nyc_taxi_trips_seed`;
DROP SCHEMA IF EXISTS `<your-catalog>`.`dbt_nyc_taxi_tutorial`;
```

All three statements should succeed. Do not add `CASCADE`: an unexpected object
should stop cleanup rather than be deleted silently.

The tutorial is now fully reversed. The local `bricks-demo` OAuth profile and
repository clone remain available for later development work.

[:lucide-wrench: Continue with the how-to guides](../how-to/index.md){ .md-button .md-button--primary }
