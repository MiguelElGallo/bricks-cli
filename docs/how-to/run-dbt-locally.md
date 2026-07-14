---
icon: lucide/laptop
---

# Run dbt locally

Use this guide to build and test the selected NYC taxi graph from your machine
against a development schema in Databricks.

## Prerequisites

You need:

- Python 3.10–3.13 (3.13 is tested; see [Runtime versions](../reference/runtime-versions.md));
- the repository checked out locally;
- an OAuth U2M profile created with `databricks auth login`;
- a SQL warehouse ID and writable catalog; and
- a dedicated development schema.

The examples use profile `bricks-demo` and schema `dbt_nyc_taxi_dev`.

## Install the development dependencies

From the repository root, create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
```

Verify dbt Core and its adapter:

```bash
dbt --version
```

The output should list both `dbt-core` and `databricks` without a compatibility
error.

## Export the connection values

Set the workspace and SQL warehouse values. `DBT_HOST` intentionally omits the
URL scheme:

```bash
export DATABRICKS_HOST="https://dbc-xxxxxxxx-xxxx.cloud.databricks.com"
export DBT_HOST="${DATABRICKS_HOST#https://}"
export DBT_HTTP_PATH="/sql/1.0/warehouses/<your-warehouse-id>"
export DBT_CATALOG="<your-catalog>"
export DBT_SCHEMA="dbt_nyc_taxi_dev"
```

Get a short-lived access token from the local U2M profile and expose only the
token value to dbt:

```bash
export DBT_ACCESS_TOKEN="$(
  databricks auth token --profile bricks-demo --output json |
    python -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
)"
```

Confirm that all five dbt variables are present without printing the token:

```bash
test -n "$DBT_HOST"
test -n "$DBT_HTTP_PATH"
test -n "$DBT_CATALOG"
test -n "$DBT_SCHEMA"
test -n "$DBT_ACCESS_TOKEN"
```

All commands should exit silently with status `0`. Re-run the token export when
you start a new shell or after a long pause; do not create a PAT for this flow.

## Preview the selected graph

List the resources that the build will select:

```bash
dbt list \
  --select "+nyc_taxi_trips" \
  --profiles-dir dbt_profiles \
  --target dev \
  --output name
```

The output should include `nyc_taxi_trips_seed`, `nyc_taxi_trips`, and the two
`not_null` tests.

## Build and test

Run the selected graph:

```bash
dbt build \
  --select "+nyc_taxi_trips" \
  --profiles-dir dbt_profiles \
  --target dev \
  --quiet \
  --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'
```

The command should exit with status `0`. [`dbt build`](https://docs.getdbt.com/reference/commands/build)
loads the seed, materializes the table, and executes the selected tests in DAG
order.

Preview five output rows:

```bash
dbt show \
  --select nyc_taxi_trips \
  --limit 5 \
  --profiles-dir dbt_profiles \
  --target dev
```

The preview should contain typed pickup/drop-off timestamps and a derived
`trip_minutes` column. Your local dbt loop is now working against
`<your-catalog>.dbt_nyc_taxi_dev`.

## Related

- [Add a dbt model](add-a-model.md)
- [Change the deployed dbt selection](change-the-deployed-selection.md)
- [Configuration values](../reference/configuration-values.md)
