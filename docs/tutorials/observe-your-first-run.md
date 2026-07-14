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
`100` rows and an average trip duration of roughly `26` minutes.

## Confirm the capture

In the same SQL editor, query the exact observability schema name recorded from
`databricks bundle summary`:

```sql
SELECT
  generated_at,
  upstream_result_state,
  capture_status,
  staging_cleanup_status,
  invocation_status,
  total_nodes,
  failed_nodes
FROM `<your-catalog>`.`<observability-schema-from-summary>`.`dbt_run_health`
ORDER BY generated_at DESC
LIMIT 1;
```

The newest row should report:

| Column | Expected value |
|---|---|
| `upstream_result_state` | `success` |
| `capture_status` | `COMPLETE` |
| `staging_cleanup_status` | `DELETED` |
| `invocation_status` | `success` |
| `total_nodes` | `4` |
| `failed_nodes` | `0` |

The four dbt nodes are the seed, model, and two tests. The collector does not
publish raw SQL, free-form messages, or credentials through this view.

You have completed the end-to-end path: one dbt result and one independently
captured evidence result, using only Databricks-native services.

[:lucide-arrow-right: Clean up the tutorial](clean-up-the-tutorial.md){ .md-button .md-button--primary }
