---
icon: lucide/blocks
---

# dbt project

`dbt_project.yml` defines one self-contained dbt Core project with two committed
demo seeds, three models at distinct grains, and ten data tests.

## Project contract

| Field | Value |
|-------|-------|
| `name` | `bricks_cli_dbt` |
| `version` | `1.0.0` |
| `config-version` | `2` |
| `profile` | `bricks_cli_dbt` |
| Anonymous usage statistics | disabled with `flags.send_anonymous_usage_stats: false` |

The project follows the official [dbt project configuration](https://docs.getdbt.com/reference/dbt_project.yml)
and [Databricks adapter](https://docs.getdbt.com/docs/core/connect-data-platform/databricks-setup)
contracts.

## Paths

| Resource type | Path |
|---------------|------|
| Models | `src/models` |
| Analyses | `src/analyses` |
| Data tests | `src/tests` |
| Seeds | `src/seeds` |
| Macros | `src/macros` |
| Snapshots | `src/snapshots` |
| Clean targets | `target`, `dbt_packages` |

Paths may be empty; dbt still treats them as configured project locations.

## DAG

```text
seed.bricks_cli_dbt.nyc_taxi_trips_seed
  → model.bricks_cli_dbt.nyc_taxi_trips
    → not_null(nyc_taxi_trips.pickup_at)
    → not_null(nyc_taxi_trips.dropoff_at)

seed.bricks_cli_dbt.weather_daily_seed
  ├─→ two seed not-null tests
  └─→ model.bricks_cli_dbt.weather_daily_observations
      ├─→ observation-key and range tests
      └─→ model.bricks_cli_dbt.weather_station_summary
          └─→ station-key and reconciliation tests
```

The source job selects both `+nyc_taxi_trips` and
`+weather_station_summary`, so one `dbt build` includes both complete ancestor
graphs and their attached tests.

## Seeds

`src/seeds/nyc_taxi/nyc_taxi_trips_seed.csv` contains 101 rows with six
columns. `dbt_project.yml` fixes their load types:

| Column | dbt seed type |
|--------|---------------|
| `tpep_pickup_datetime` | `timestamp` |
| `tpep_dropoff_datetime` | `timestamp` |
| `trip_distance` | `double` |
| `fare_amount` | `double` |
| `pickup_zip` | `int` |
| `dropoff_zip` | `int` |

`src/seeds/weather/weather_daily_seed.csv` contains eight explicitly synthetic
rows for two demo stations. Its configured types are `STRING` identifiers and
names, a `DATE` observation key, and `DOUBLE` weather measures. The values are
invented for deterministic testing and are not meteorological records.

## Model outputs

`src/models/nyc_taxi/nyc_taxi_trips.sql` materializes a table with:

| Column | Expression/type |
|--------|-----------------|
| `pickup_at` | pickup timestamp |
| `dropoff_at` | drop-off timestamp |
| `trip_distance` | `DOUBLE` |
| `fare_amount` | `DOUBLE` |
| `pickup_zip` | `INT` |
| `dropoff_zip` | `INT` |
| `trip_minutes` | rounded timestamp difference in minutes |

`pickup_at` and `dropoff_at` have `not_null` tests. The model configuration is
`table` both at directory scope and explicitly in the model.

`weather_daily_observations` is a view at one row per station and date. It adds
a stable observation key, mean temperature, temperature range, and wet-day
flag. `weather_station_summary` is a Delta table at one row per station with
period dates, counts, temperature extrema, precipitation, and wet-day totals.
Key tests plus singular range and reconciliation tests protect both grains.

## Connection paths

| Execution | Profile source | Credentials |
|-----------|----------------|-------------|
| Local dbt | `dbt_profiles/profiles.yml` | `DBT_*` environment variables |
| Deployed source job | Databricks-generated profile from `warehouse_id`, `catalog`, and `schema` | Injected for the job `run_as` identity |

The deployed command deliberately omits dbt `--target`; its generated profile
has a Databricks-managed target. The command does set `--target-path`, which
controls JSON artifact output only.

`profile_template.yml` is an optional `dbt init` prompt template and is not used
by CI or either deployed job. It uses the AWS workspace-host shape and points to
`databricks auth token <profile> --output json` for a short-lived local token;
the committed environment-only profile remains the reproducible project path.

## Example

```bash
dbt parse --no-partial-parse --profiles-dir dbt_profiles --target dev
dbt list --profiles-dir dbt_profiles --target dev --output name
```
