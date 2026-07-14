---
icon: lucide/rocket
---

# Deploy and run the source job

We will configure an isolated development target, preview it, deploy it, and run
the source dbt job once. Development mode pauses both schedules and prefixes
the deployed resources, so this tutorial does not create an active production
schedule.

## Export the tutorial values

Use the warehouse ID and catalog name you copied on the connection page:

```bash
export BUNDLE_VAR_warehouse_id="<your-warehouse-id>"
export BUNDLE_VAR_catalog="<your-catalog>"
export BUNDLE_VAR_schema="dbt_nyc_taxi_tutorial"
export BUNDLE_VAR_observability_schema="dbt_observability_tutorial"
export BUNDLE_VAR_observability_staging_volume="dbt_artifacts_staging"
export BUNDLE_VAR_observability_volume="dbt_artifacts"
```

Keep the tutorial schema names exactly as shown. They isolate the tutorial data
from other dbt development work.

Confirm the two workspace-specific values are no longer placeholders:

```bash
printf 'warehouse=%s\ncatalog=%s\n' \
  "$BUNDLE_VAR_warehouse_id" \
  "$BUNDLE_VAR_catalog"
```

The output should contain your real warehouse ID and catalog name.

## Validate the bundle

Resolve the `dev` target:

```bash
databricks bundle validate --target dev --profile bricks-demo
```

The command should end with `Validation OK!` and identify `dev` as the target.
If either required input was not exported, validation stops with a missing
variable error before any workspace resource changes.

## Preview the deployment

Create a read-only plan:

```bash
databricks bundle plan --target dev --profile bricks-demo
```

The plan should propose development copies of:

- source job `nyc_taxi_dbt_job`;
- collector job `nyc_taxi_dbt_observability_collector`;
- a target-scoped observability schema; and
- staging and evidence managed Volumes.

No bundle-managed job, schema, or Volume has been applied yet. Validation or
planning can still initialize the target's workspace deployment directory.

## Deploy the development copy

Deploy the plan:

```bash
databricks bundle deploy --target dev --profile bricks-demo
```

The command uploads the bundle files and creates the resources directly through
Databricks APIs. It should finish with `Deployment complete!`.

Summarize the deployed resources:

```bash
databricks bundle summary --target dev --profile bricks-demo
```

The summary should show both jobs and their workspace URLs. Record the exact
observability schema name shown in the summary; development mode can prefix the
configured base name. We will use that exact name in the next page.

## Run the source job

Start the dbt build and wait for its result:

```bash
databricks bundle run nyc_taxi_dbt_job \
  --target dev \
  --profile bricks-demo
```

The command should finish with a successful run URL. In the workspace, the
`dbt_nyc_taxi` task should be `TERMINATED` with result `SUCCESS`.

That result belongs only to dbt: the seed loaded, the table materialized, and
the two data tests passed. Artifact capture is the next, separate result.

[:lucide-arrow-right: Observe your first run](observe-your-first-run.md){ .md-button .md-button--primary }
