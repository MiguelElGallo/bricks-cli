---
icon: lucide/git-compare-arrows
---

# How project changes appear in observability

Four real dbt attempts show the boundary clearly: repeating unchanged code
creates a new attempt with the same node shape, adding one seed row changes the
seed fact without changing the graph, and adding a second topic expands the
normalized node set from 4 to 15.

All four attempts ran on July 15, 2026 in the same Databricks source job and
task, with a distinct [AttemptKey](../reference/attempt-key.md) for each. The
values below were queried from the sanitized `dbt_run_health` and
`dbt_node_health` views. Restricted tables were used only for the aggregate
idempotency and archive checks, through temporary access that was revoked after
the queries.

## The controlled changes

| Phase | Deployed change | Provenance |
|---|---|---|
| Baseline A | 100-row taxi seed; one model; two tests | [commit `fc296dec`](https://github.com/MiguelElGallo/bricks-cli/commit/fc296dec7f50fb3f73e526e9f5b5f9efb69da705); protected deployment |
| Baseline B | No change; controlled repeat of baseline A | same `fc296dec` deployment |
| Taxi 101 | Appended the next chronological row from Databricks' public `samples.nyctaxi.trips` table | [commit `47d44c4`](https://github.com/MiguelElGallo/bricks-cli/commit/47d44c4d8ed620f8cac540adba5f8be72a02dce5); protected deployment |
| Weather graph | Added an eight-row synthetic weather seed, two models, and eight tests | [commit `188fdb1`](https://github.com/MiguelElGallo/bricks-cli/commit/188fdb1746d909dba9ee5e83553b7d15ffb27d6e); protected deployment |

The weather values are invented for this public demo. They contain no Personal
Data and are not meteorological records.

## Run-level comparison

Every attempt had upstream result `success`, invocation result `success`,
capture status `COMPLETE`, cleanup status `DELETED`, and zero warning, failed,
or skipped nodes.

| Phase | Artifacts generated (UTC) | Captured (UTC) | dbt elapsed (s) | Seeds | Models | Tests | Taxi seed rows affected |
|---|---|---|---:|---:|---:|---:|---:|
| Baseline A | `03:19:35.365` | `03:20:56.018` | `44.456` | `1` | `1` | `2` | `100` |
| Baseline B | `03:51:59.341` | `03:53:25.924` | `40.449` | `1` | `1` | `2` | `100` |
| Taxi 101 | `04:09:30.534` | `04:10:32.452` | `15.615` | `1` | `1` | `2` | `101` |
| Weather graph | `04:31:50.315` | `04:32:58.117` | `26.621` | `2` | `3` | `10` | `101` |

The two baselines prove that a new AttemptKey does not imply a project change.
Their node identities, statuses, and seed row count matched even though their
durations and compressed archive sizes differed. The seed change then appeared
as `rows_affected = 101` while the graph stayed at four nodes. The weather
change produced a new 15-node shape while retaining the 101-row taxi seed.

## Final 15-node capture

This is the complete safe node projection from the final
`dbt_node_health` result. `NULL` means dbt did not report that field; it does
not mean zero.

| Resource | Node | Status | Elapsed (s) | Failures | Rows affected |
|---|---|---|---:|---:|---:|
| seed | `nyc_taxi_trips_seed` | `success` | `6.569` | `NULL` | `101` |
| seed | `weather_daily_seed` | `success` | `6.354` | `NULL` | `8` |
| model | `nyc_taxi_trips` | `success` | `6.013` | `NULL` | `NULL` |
| model | `weather_daily_observations` | `success` | `1.906` | `NULL` | `NULL` |
| model | `weather_station_summary` | `success` | `5.472` | `NULL` | `NULL` |
| test | `not_null_nyc_taxi_trips_dropoff_at` | `pass` | `3.913` | `0` | `NULL` |
| test | `not_null_nyc_taxi_trips_pickup_at` | `pass` | `3.594` | `0` | `NULL` |
| test | `not_null_weather_daily_observations_weather_observation_key` | `pass` | `3.656` | `0` | `NULL` |
| test | `not_null_weather_daily_seed_observation_date` | `pass` | `3.014` | `0` | `NULL` |
| test | `not_null_weather_daily_seed_station_id` | `pass` | `3.608` | `0` | `NULL` |
| test | `not_null_weather_station_summary_station_id` | `pass` | `2.636` | `0` | `NULL` |
| test | `unique_weather_daily_observations_weather_observation_key` | `pass` | `3.228` | `0` | `NULL` |
| test | `unique_weather_station_summary_station_id` | `pass` | `2.773` | `0` | `NULL` |
| test | `weather_daily_observation_ranges` | `pass` | `3.974` | `0` | `NULL` |
| test | `weather_station_summary_invariants` | `pass` | `3.661` | `0` | `NULL` |

The collector does not need a new schema when the dbt graph grows. Each node is
another normalized fact keyed by the attempt and dbt `unique_id`.

## Model output beside observability

The health views do not expose relation data. To verify what the models built,
the production relations were queried separately with aggregate-only SQL:

| Output | Observed rows or days | Queried aggregate values |
|---|---:|---|
| `nyc_taxi_trips` | `101` rows | average trip duration `26.28` minutes |
| `weather_daily_seed` | `8` rows | explicitly synthetic input |
| `weather_daily_observations` | `8` rows | one row per station and date |
| `HEL_DEMO` station summary | `4` days | average mean `17.38` °C; period min/max `12.0`/`24.0` °C; precipitation `8.6` mm; `2` wet days |
| `NYC_DEMO` station summary | `4` days | average mean `25.75` °C; period min/max `20.0`/`32.0` °C; precipitation `17.1` mm; `3` wet days |

This distinction matters: observability proves execution facts and selected dbt
metadata. It does not copy model rows into telemetry tables.

## Idempotent persistence

Each controlled attempt was swept at least once; the protected deployments ran
the collector twice. Repeated sweeps left one normalized fact per logical key:

| Phase | Registry rows | Invocation rows | Node rows | Distinct node keys | Archive files | Compressed bytes |
|---|---:|---:|---:|---:|---:|---:|
| Baseline A | `1` | `1` | `4` | `4` | `2` | `107,343` |
| Baseline B | `1` | `1` | `4` | `4` | `2` | `108,882` |
| Taxi 101 | `1` | `1` | `4` | `4` | `2` | `108,735` |
| Weather graph | `1` | `1` | `15` | `15` | `2` | `114,801` |

The two files are `manifest.json` and `run_results.json`. Archive size can vary
between unchanged invocations, so it is a storage and capacity observation, not
an integrity control or project-diff signal.

## What to infer—and what not to infer

- A separate AttemptKey proves a separate task attempt, not a code change.
- Node identities and resource counts show graph shape; they do not prove that
  relation contents are identical.
- Seed `rows_affected` made the 100-to-101 change visible. Adapter-reported
  model `rows_affected` remained `NULL`, so model row counts were verified
  separately.
- Durations naturally vary with warehouse and platform conditions. Baseline B
  being faster than baseline A is not evidence of a project optimization.
- Whole-artifact hashes can differ because manifests contain invocation
  metadata. Do not use an archive or manifest digest as a semantic graph diff.
- Sanitized views deliberately exclude compiled SQL, raw JSON, logs, free-form
  messages, adapter responses, archive paths, and relation rows.

For the reusable query pattern, see
[Compare exact attempts](../how-to/query-job-health.md#compare-exact-attempts).
For the field contract, see
[Observability objects](../reference/observability-objects.md).

!!! note "Sanitized public evidence"

    This page omits workspace, account, job, task, collector, warehouse,
    catalog, schema, principal, invocation, and archive identifiers; Databricks
    archive paths; archive and manifest hashes; raw artifacts; compiled SQL;
    logs; messages; adapter responses; and taxi relation rows. Only public or
    synthetic demo-data aggregates and allowlisted operational facts are shown.
