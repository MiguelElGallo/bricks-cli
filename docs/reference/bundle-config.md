---
icon: lucide/file-cog
---

# Bundle configuration

`databricks.yml` is the root of the bundle. This page documents the file as it
ships in the repo.

## `bundle`

```yaml
bundle:
  name: bricks_cli_dbt
  uuid: b678d035-88c4-470e-8bf4-2e81accd95f5
```

| Field | Meaning |
|-------|---------|
| `name` | Identifies the project; used in resource paths and `[dev <user>]` prefixes |
| `uuid` | Stable identifier for the bundle |

## `include`

```yaml
include:
  - resources/*.yml
```

Globs that compose the configuration. The job lives in
`resources/nyc_taxi.job.yml`, so resource definitions stay separate from targets.
See [The dbt job resource](job-resource.md).

## `variables`

Every workspace-specific value is a bundle variable, so no real host, warehouse,
catalog, or user is committed:

```yaml
variables:
  warehouse_id:
    description: ID of the SQL warehouse the dbt task runs against.
    default: REPLACE_WITH_YOUR_WAREHOUSE_ID
  catalog:
    description: Unity Catalog catalog dbt writes to.
    default: REPLACE_WITH_YOUR_CATALOG
  schema:
    description: Schema dbt builds objects in.
    default: dbt_nyc_taxi
```

The `warehouse_id` and `catalog` defaults are deliberately obvious placeholders;
`schema` defaults to the safe, non-sensitive value `dbt_nyc_taxi`. Supply real
values at deploy time via `BUNDLE_VAR_*` — see
[Configuration values](configuration-values.md).

!!! note "Where the host comes from"
    There is intentionally **no** `workspace.host` in the file. The CLI resolves
    the host from `DATABRICKS_HOST` or your selected profile, so the host is never
    committed either.

## `targets`

Named environments. `dev` is the default; `prod` deploys to a fixed path under the
**deploying principal's** home directory (in CI, that's the service principal) and
applies explicit permissions.

```yaml
targets:
  dev:
    mode: development
    default: true

  prod:
    mode: production
    workspace:
      root_path: /Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}
    permissions:
      - user_name: ${workspace.current_user.userName}
        level: CAN_MANAGE
```

| Field | Meaning |
|-------|---------|
| `mode: development` | Prefixes resources with `[dev <user>]`, pauses schedules, marks dev copies |
| `mode: production` | Deploys "for real" to a `root_path` under the deploying principal's home (the CI service principal in automation), with declared permissions |
| `default: true` | Used when `--target` is omitted |
| `${workspace.current_user.userName}` | Resolved at deploy time — no hard-coded user name |

!!! tip "Deployment modes"
    `development` mode is what makes the `dev` target safe to iterate in: nothing
    fires on a schedule and every resource is clearly tagged. Background:
    [Why Declarative Automation Bundles](../explanation/why-asset-bundles.md).

## Selecting a target

```bash
databricks bundle <command> --target dev    # or: -t prod
```

Or set `DATABRICKS_BUNDLE_TARGET` (the older `DATABRICKS_BUNDLE_ENV` is a
deprecated alias).
