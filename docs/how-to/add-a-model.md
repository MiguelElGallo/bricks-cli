---
icon: lucide/file-plus
---

# Add a dbt model

Use this guide to add and validate one model named `long_trips`. It creates a
reusable relation for trips lasting at least 30 minutes while preserving the
upstream model's one-row-per-trip grain.

## Prerequisites

Complete [Run dbt locally](run-dbt-locally.md) first. Keep its virtual
environment and `DBT_*` variables active, and use a development schema.

## Create the model

Create `src/models/nyc_taxi/long_trips.sql` with this SQL:

```sql title="src/models/nyc_taxi/long_trips.sql"
{{ config(materialized = 'table') }}

with trips as (

    select * from {{ ref('nyc_taxi_trips') }}

)

select *
from trips
where trip_minutes >= 30
```

The model uses
[`ref()`](https://docs.getdbt.com/reference/dbt-jinja-functions/ref) instead of
a hard-coded relation, so dbt records the dependency on `nyc_taxi_trips`.

## Document and test it

Append this item under the existing `models:` list in
`src/models/nyc_taxi/schema.yml`:

```yaml title="src/models/nyc_taxi/schema.yml"
  - name: long_trips
    description: >
      NYC taxi trips lasting at least 30 minutes. One row per trip, filtered
      from nyc_taxi_trips.
    columns:
      - name: pickup_at
        description: "Trip start timestamp."
        data_tests:
          - not_null
```

Do not add a second `models:` key. The new item must align with the existing
`- name: nyc_taxi_trips` item. The `not_null` assertion becomes part of the
selected build.

## Preview the graph

List the new model and its ancestors:

```bash
dbt list \
  --select "+long_trips" \
  --profiles-dir dbt_profiles \
  --target dev \
  --output name
```

The output should include the seed, `nyc_taxi_trips`, `long_trips`, and their
selected tests. If `long_trips` is absent, correct the file path or YAML before
running warehouse work.

## Build and inspect the model

Build the model, its ancestors, and selected tests:

```bash
dbt build \
  --select "+long_trips" \
  --profiles-dir dbt_profiles \
  --target dev \
  --quiet \
  --warn-error-options '{"error":["NoNodesForSelectionCriteria"]}'
```

The command should exit with status `0`.

Preview the result:

```bash
dbt show \
  --select long_trips \
  --limit 5 \
  --profiles-dir dbt_profiles \
  --target dev
```

Every displayed row should have `trip_minutes >= 30`. The model is now valid
locally, but the deployed source job still selects its original graph. Update
that selection separately with
[Change the deployed dbt selection](change-the-deployed-selection.md).
