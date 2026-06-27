---
icon: lucide/briefcase
---

# The dbt job resource

`resources/nyc_taxi.job.yml` defines the single resource in this bundle: a job
that runs dbt on **serverless** compute. Here it is, field by field.

```yaml
resources:
  jobs:
    nyc_taxi_dbt_job:
      name: nyc_taxi_dbt_job

      trigger:
        periodic:
          interval: 1
          unit: DAYS

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

## Fields

| Field | Meaning |
|-------|---------|
| `name` | Display name of the job in the workspace |
| `trigger.periodic` | Runs daily; **paused automatically** in the `dev` target (development mode) |
| `tasks[].task_key` | Identifier for the task |
| `tasks[].environment_key` | Links the task to the serverless `environments` spec below |
| `dbt_task.project_directory` | `../` — the dbt project is the bundle root |
| `dbt_task.warehouse_id` | SQL warehouse, from `${var.warehouse_id}` |
| `dbt_task.catalog` | Unity Catalog catalog, from `${var.catalog}` |
| `dbt_task.schema` | Target schema, from `${var.schema}` |
| `dbt_task.commands` | The dbt commands to run, in order |
| `environments[].spec.environment_version` | Serverless environment version (`"4"`) |
| `environments[].spec.dependencies` | Python deps installed into the environment |

## Why there's no `--target`

The `commands` are bare `dbt seed` / `dbt run` / `dbt test` — **no `--target`
flag**. When `warehouse_id` / `catalog` / `schema` are set on the `dbt_task`,
Databricks **generates** the dbt profile and a single target from them, and
injects `DBT_HOST` / `DBT_ACCESS_TOKEN`. Passing `--target dev` would fail,
because that generated profile has no target by that name.

!!! info "The bundle target, not a dbt target, picks the environment"
    `--target dev` / `--target prod` on the **bundle** selects which workspace
    you deploy to. The dbt task always runs against the warehouse/catalog/schema
    you supplied as bundle variables. Full explanation:
    [How dbt connects to Databricks](../explanation/how-dbt-connects.md).

## Supplying the variables

| Bundle variable | Local env var | GitHub Variable (CI) |
|-----------------|---------------|----------------------|
| `warehouse_id` | `BUNDLE_VAR_warehouse_id` | `DATABRICKS_WAREHOUSE_ID` |
| `catalog` | `BUNDLE_VAR_catalog` | `DATABRICKS_CATALOG` |
| `schema` | `BUNDLE_VAR_schema` | `DATABRICKS_SCHEMA` |

See [Configuration values](configuration-values.md) for the complete table.
