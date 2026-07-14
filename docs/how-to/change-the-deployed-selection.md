---
icon: lucide/git-branch
---

# Change the deployed dbt selection

Use this guide to make the deployed source job build `long_trips` and all of its
ancestors instead of stopping at `nyc_taxi_trips`.

## Prerequisites

- Add and locally validate `long_trips` with [Add a dbt model](add-a-model.md).
- Keep the local dbt `DBT_*` values active.
- Export the same development `BUNDLE_VAR_*` values used for the existing
  bundle deployment.
- Use the OAuth U2M profile that owns the development copy. The examples use
  `bricks-demo`.

## Preview the selector

Ask dbt what `+long_trips` selects before changing the job:

```bash
dbt list \
  --select "+long_trips" \
  --profiles-dir dbt_profiles \
  --target dev \
  --output name
```

The output should include `nyc_taxi_trips_seed`, `nyc_taxi_trips`,
`long_trips`, and their selected tests. The leading `+` selects ancestors; see
the official [node-selection syntax](https://docs.getdbt.com/reference/node-selection/syntax).

## Change the job command

Open `resources/nyc_taxi.job.yml` and find the dbt command's selector:

```yaml
--select +nyc_taxi_trips
```

Replace only that selector with:

```yaml
--select +long_trips
```

Review the change:

```bash
git diff -- resources/nyc_taxi.job.yml
```

The diff should contain one selector-line replacement. Keep the existing
`--target-path`, `--quiet`, and warning options unchanged; the artifact contract
depends on them.

## Validate and deploy the change

Resolve and preview the development target:

```bash
databricks bundle validate --target dev --profile bricks-demo
databricks bundle plan --target dev --profile bricks-demo
```

Validation should succeed, and the plan should show an update to the source job
without replacing the observability storage.

Deploy the update:

```bash
databricks bundle deploy --target dev --profile bricks-demo
```

The command should finish with `Deployment complete!`.

## Verify the deployed selector

Run the source job and then the paused development collector:

```bash
databricks bundle run nyc_taxi_dbt_job \
  --target dev \
  --profile bricks-demo

databricks bundle run dbt_observability_collector_job \
  --target dev \
  --profile bricks-demo
```

Both runs should succeed. The new source run's dbt artifacts now contain
`long_trips`, while the collector continues to use the same attempt-keyed
staging and evidence contract.
