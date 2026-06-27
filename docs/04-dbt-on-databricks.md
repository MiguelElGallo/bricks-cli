# 04 – dbt on Databricks

This project uses the **`dbt-databricks`** adapter (the official, Databricks‑maintained
dbt adapter). The dbt scope is intentionally minimal — **one seed, one table** — so
the focus stays on deployment.

## The adapter

`requirements-dev.txt` pins it for local development, and the deployed job installs
the same range into its serverless environment:

```
dbt-databricks>=1.8.0,<2.0.0
```

`dbt-databricks` connects to a **SQL warehouse** over its HTTP path and builds
objects in **Unity Catalog** (`catalog.schema.object`). It supports
materializations including `view`, `table`, `incremental`, `materialized_view`,
`streaming_table`, and `ephemeral`. This demo uses a plain `table`.

## Project structure

Paths are configured in `dbt_project.yml` to live under `src/` so non‑dbt bundle
resources can sit alongside them:

```
dbt_project.yml                      # name/profile + path + seed/model config
src/
├── seeds/nyc_taxi/
│   ├── nyc_taxi_trips_seed.csv      # 100 rows from samples.nyctaxi.trips
│   └── properties.yml               # seed docs
└── models/nyc_taxi/
    ├── nyc_taxi_trips.sql           # the table model
    └── schema.yml                   # model docs + tests
```

## Seed → table (the whole pipeline)

**1. The seed.** `dbt seed` loads the committed CSV into the warehouse. Column
types are declared so the raw load is well‑typed (in `dbt_project.yml`):

```yaml
seeds:
  bricks_cli_dbt:
    nyc_taxi:
      nyc_taxi_trips_seed:
        +column_types:
          tpep_pickup_datetime: timestamp
          tpep_dropoff_datetime: timestamp
          trip_distance: double
          fare_amount: double
          pickup_zip: int
          dropoff_zip: int
```

**2. The table.** The single model reads the seed via `ref()` and materializes a
Delta table, adding light typing and one derived column:

```sql
{{ config(materialized = 'table') }}

with source as ( select * from {{ ref('nyc_taxi_trips_seed') }} )

select
    cast(tpep_pickup_datetime as timestamp)  as pickup_at,
    …,
    round(timestampdiff(SECOND, tpep_pickup_datetime, tpep_dropoff_datetime)/60.0, 2) as trip_minutes
from source
```

The seed and the model have **different names** (`…_seed` vs `nyc_taxi_trips`) on
purpose: dbt resource names must be unique, and `ref()` resolves by name.

**3. Tests.** `schema.yml` adds `not_null` tests that `dbt test` checks after the
build.

## How dbt connects

The deployed job and local runs use **different** connection paths — and neither
stores a workspace identifier or credential in the repo:

- **Deployed job:** the dbt task in `resources/nyc_taxi.job.yml` names the SQL
  warehouse, catalog and schema directly (from bundle variables). Databricks
  builds the dbt profile from those and injects `DBT_HOST` / `DBT_ACCESS_TOKEN`.
- **Local dev:** `dbt_profiles/profiles.yml` is used. It reads every
  workspace‑specific value from environment variables:

```yaml
bricks_cli_dbt:
  target: dev
  outputs:
    dev:
      type: databricks
      method: http
      catalog:   "{{ env_var('DBT_CATALOG') }}"
      schema:    "{{ env_var('DBT_SCHEMA', 'dbt_nyc_taxi') }}"
      http_path: "{{ env_var('DBT_HTTP_PATH') }}"
      threads: 4
      host:  "{{ env_var('DBT_HOST') }}"
      token: "{{ env_var('DBT_ACCESS_TOKEN') }}"
```

Because every value is an env var, the file is safe to commit — there is no host,
warehouse id, catalog, or token in it.

## Running dbt locally

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# Point dbt at your workspace + warehouse via env vars (nothing is committed).
# On Azure you can mint a short‑lived Entra ID token instead of a PAT
# (2ff814a6-… is the Azure Databricks programmatic resource id):
export DBT_HOST="adb-XXXXXXXXXXXX.NN.azuredatabricks.net"
export DBT_HTTP_PATH="/sql/1.0/warehouses/<your-warehouse-id>"
export DBT_CATALOG="<your-catalog>"
export DBT_ACCESS_TOKEN="$(az account get-access-token \
  --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv)"

dbt seed --profiles-dir dbt_profiles --target dev
dbt run  --profiles-dir dbt_profiles --target dev
dbt test --profiles-dir dbt_profiles --target dev
```

Prefer interactive setup? `dbt init` uses `profile_template.yml` to prompt for the
host, warehouse HTTP path, catalog and schema (no real values are stored) and
writes a profile into `~/.dbt/profiles.yml`.

## The serverless dbt task (how the job runs dbt)

`resources/nyc_taxi.job.yml` runs dbt on **serverless job compute** — no cluster
to size. The warehouse, catalog and schema come from **bundle variables**, so the
job definition carries no hard‑coded environment:

```yaml
tasks:
  - task_key: dbt_nyc_taxi
    environment_key: default
    dbt_task:
      project_directory: ../
      warehouse_id: ${var.warehouse_id}
      catalog: ${var.catalog}
      schema: ${var.schema}
      commands:
        - 'dbt seed'
        - 'dbt run'
        - 'dbt test'
environments:
  - environment_key: default
    spec:
      environment_version: "4"
      dependencies:
        - dbt-databricks>=1.8.0,<2.0.0
```

Supply real values at deploy time — locally as `BUNDLE_VAR_warehouse_id` /
`BUNDLE_VAR_catalog` / `BUNDLE_VAR_schema`, and in CI as GitHub repository
Variables (see [docs/05](05-deploy-and-run.md)). From those task fields Databricks
**generates** the dbt profile and target and injects `DBT_HOST` /
`DBT_ACCESS_TOKEN`; that generated target is why the commands omit `--target`.

## dbt agent skills

The official [dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills)
are installed under `.agents/skills/` (via the Vercel `skills` CLI):

```bash
npx skills add dbt-labs/dbt-agent-skills/skills/dbt --agent github-copilot --skill '*' -y --copy
```

These are [Agent Skills](https://agentskills.io/) — folders of instructions an AI
agent loads automatically when your request matches (e.g.
`using-dbt-for-analytics-engineering`, `running-dbt-commands`,
`adding-dbt-unit-test`). They make an agent more accurate at writing and running
dbt for the **dbt-databricks** adapter used here. `skills-lock.json` records the
installed set.

---
Next: [05 – Deploy & run](05-deploy-and-run.md).
