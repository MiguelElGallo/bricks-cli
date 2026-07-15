---
icon: lucide/activity
---

# Observe your first run

The source job has finished. We will now run the independent collector, confirm
the dbt table, and inspect the sanitized capture record. All evidence remains in
Databricks.

## Run the collector

The development collector schedule is paused, so start one sweep manually:

```bash
databricks bundle run dbt_observability_collector_job \
  --target dev \
  --profile bricks-demo
```

The command should finish successfully. The collector has now:

1. found the completed source task through the Jobs API;
2. read its `manifest.json` and `run_results.json` from staging;
3. written a content-addressed archive to the evidence Volume;
4. written allowlisted facts to Delta tables; and
5. deleted the reconciled staging leaf.

The source run and collector run remain two independent Lakeflow job results.

## Confirm the dbt output

Open a Databricks SQL editor attached to the tutorial warehouse and run:

```sql
SELECT
  count(*) AS rows,
  round(avg(trip_minutes), 2) AS average_trip_minutes
FROM `<your-catalog>`.`dbt_nyc_taxi_tutorial`.`nyc_taxi_trips`;
```

Replace `<your-catalog>` with the value you exported. The result should contain
`101` rows and an average trip duration of roughly `26` minutes.

Query the synthetic station summary too:

```sql
SELECT
  station_id,
  observation_days,
  average_mean_temp_c,
  total_precipitation_mm,
  wet_days
FROM `<your-catalog>`.`dbt_nyc_taxi_tutorial`.`weather_station_summary`
ORDER BY station_id;
```

The result has two rows. `HEL_DEMO` reports four days, `17.38` °C average
mean temperature, `8.6` mm precipitation, and two wet days. `NYC_DEMO` reports
four days, `25.75` °C, `17.1` mm, and three wet days. These values are
explicitly synthetic and exist only to make the dbt graph deterministic.

## Confirm the capture

In the same SQL editor, query the exact observability schema name recorded from
`databricks bundle summary`:

```sql
SELECT
  generated_at,
  captured_at,
  dbt_version,
  adapter_type,
  command,
  upstream_result_state,
  capture_status,
  staging_cleanup_status,
  invocation_status,
  elapsed_seconds,
  total_nodes,
  success_nodes,
  warning_nodes,
  failed_nodes,
  skipped_nodes
FROM `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_run_health`
ORDER BY generated_at DESC
LIMIT 1;
```

## See one real reference capture

This dated snapshot came from a protected deployment of
[commit `48a608c`](https://github.com/MiguelElGallo/bricks-cli/commit/48a608c35dd04260668cdca2548df6b2ce0895c5)
on July 14, 2026. That workflow exercised the repository's `prod` target;
these are not values copied from your tutorial run. Run- and node-level values
were copied from the sanitized `dbt_run_health` and `dbt_node_health` views.

The archive and idempotency summaries came from a temporary, least-privilege
verification query against restricted tables. No raw artifact was opened or
exported. This is one observed successful run, not an output contract. It
predates the weather graph and preserves the earlier four-node taxi-only shape
as historical evidence. Your timestamps, dbt version, durations, and archive
sizes may differ. The current unmodified tutorial graph resolves to 15 nodes;
it should still report `success`, `COMPLETE`, `DELETED`, and no warnings,
failures, or skipped nodes.

### Run-level facts

| Captured field | Observed value |
|---|---|
| Artifacts generated (`generated_at`) | `2026-07-14T21:22:26.348Z` |
| Collector recorded (`captured_at`) | `2026-07-14T21:23:34.706Z` |
| dbt version (`dbt_version`) / adapter (`adapter_type`) | `1.11.11` / `databricks` |
| Command | `build` |
| Upstream result | `success` |
| Capture (`capture_status`) / cleanup (`staging_cleanup_status`) | `COMPLETE` / `DELETED` |
| Invocation result | `success` |
| dbt elapsed time | `14.545` seconds |
| Node counts | `4` successful, `0` warning, `0` failed, `0` skipped |

### Node-level facts

| Resource | Node | Status | Elapsed (s) | Compile (s) | Execute (s) | Failures | Rows affected |
|---|---|---|---:|---:|---:|---:|---:|
| seed | `nyc_taxi_trips_seed` | `success` | `5.419` | `0.000` | `5.348` | `NULL` | `100` |
| model | `nyc_taxi_trips` | `success` | `5.183` | `1.031` | `4.078` | `NULL` | `NULL` |
| test | `not_null_nyc_taxi_trips_dropoff_at` | `pass` | `1.803` | `0.488` | `1.236` | `0` | `NULL` |
| test | `not_null_nyc_taxi_trips_pickup_at` | `pass` | `2.236` | `0.580` | `1.580` | `0` | `NULL` |

`NULL` means dbt did not report a value for that field; it does not mean zero.
Elapsed time includes work outside the compile and execute phases, so those
three columns do not need to add up exactly.

### Artifact summary

| Captured field | Observed value |
|---|---|
| Required files | `2`: `manifest.json`, `run_results.json` |
| Compressed archive | `108,302` bytes |
| Uncompressed payload | `931,803` bytes |
| Manifest schema | [`https://schemas.getdbt.com/dbt/manifest/v12.json`](https://schemas.getdbt.com/dbt/manifest/v12.json) |
| Run-results schema | [`https://schemas.getdbt.com/dbt/run-results/v6.json`](https://schemas.getdbt.com/dbt/run-results/v6.json) |
| Parser contract | `1.0.0` |

### Idempotency check

The same attempt passed through two collector sweeps without creating duplicate
facts:

| Registry rows | Invocation rows | Node rows | Distinct node keys |
|---:|---:|---:|---:|
| `1` | `1` | `4` | `4` |

For this attempt, one registry record points to one dbt invocation and four
unique node results. The second sweep did not add another copy. To reproduce
the proof with the complete six-field AttemptKey, follow
[Verify a production deployment](../how-to/verify-production-deployment.md).

!!! note "Sanitized public evidence"

    This curated example uses only the repository's public demonstration data
    and contains no Personal Data. It deliberately omits the Databricks
    workspace host; workspace, job, task, collector, account, warehouse,
    catalog, schema, and principal identifiers; the dbt invocation ID; archive
    paths and hashes; manifest hashes; raw JSON; compiled SQL; logs; free-form
    messages; adapter-response objects; and relation data. See
    [Security and secret boundaries](../explanation/security-and-secrets.md)
    and the complete
    [observability object contract](../reference/observability-objects.md).

You have completed the end-to-end path: one dbt result and one independently
captured evidence result, using only Databricks-native services. Clean up the
tutorial before continuing to the explanation pages.

[:lucide-arrow-right: Clean up the tutorial](clean-up-the-tutorial.md){ .md-button .md-button--primary }
