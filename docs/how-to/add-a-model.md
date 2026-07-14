---
icon: lucide/file-plus
---

# Add a dbt model

Extend the project beyond the single `nyc_taxi_trips` table. The mechanics are
the same whether you add a model, a seed, or a test.

## Add a model

1. Create a new `.sql` file under `src/models/nyc_taxi/` (or a new subfolder).
   Reference upstream resources with `ref()`:

    ```sql title="src/models/nyc_taxi/long_trips.sql"
    {{ config(materialized = 'table') }}

    select *
    from {{ ref('nyc_taxi_trips') }}
    where trip_minutes >= 30
    ```

2. Document and test it. The project already has
   `src/models/nyc_taxi/schema.yml` (it starts with `version: 2` and a `models:`
   list), so **append** your new model under that existing `models:` list rather
   than replacing the file:

    ```yaml title="src/models/nyc_taxi/schema.yml (append under models:)"
      - name: long_trips
        description: "Trips of 30 minutes or longer."
        columns:
          - name: pickup_at
            data_tests:
              - not_null
    ```

3. Build your new model — and everything upstream of it — plus tests. The `+`
   prefix selects all ancestors, so `dbt build` loads the seed
   (`nyc_taxi_trips_seed`), builds `nyc_taxi_trips`, then `long_trips`, and runs
   the selected tests — all in dependency order:

    ```bash
    dbt build --select +long_trips --profiles-dir dbt_profiles --target dev
    ```

!!! tip "Materializations"
    `+materialized` can be `table`, `view`, `incremental`, `materialized_view`,
    `streaming_table`, or `ephemeral`. This demo defaults models to `table` (set
    in `dbt_project.yml`); override per-model with `{{ config(...) }}`.

## Add a seed

1. Drop a CSV into `src/seeds/nyc_taxi/`.
2. (Recommended) declare column types under `seeds:` in `dbt_project.yml`, the
   same way `nyc_taxi_trips_seed` does.
3. Load it:

    ```bash
    dbt seed --select your_new_seed --profiles-dir dbt_profiles --target dev
    ```

## Add it to the deployed selection

The job deliberately runs `dbt build --select +nyc_taxi_trips`; it does not
build the whole project. A model upstream of `nyc_taxi_trips` is selected by the
leading `+`, but a new downstream model such as `long_trips` is not. Preview the
selection first:

```bash
dbt list --select +nyc_taxi_trips long_trips \
  --profiles-dir dbt_profiles --target dev
```

Then extend the `--select` expression in `resources/nyc_taxi.job.yml` (or replace
it with an intentional tag/path selector), validate the bundle, and redeploy:

```bash
databricks bundle deploy -t dev -p bricks-demo
databricks bundle run nyc_taxi_dbt_job -t dev -p bricks-demo
```

## Related

- [Run dbt locally](run-dbt-locally.md)
- Reference: [The dbt job resources](../reference/job-resource.md)
