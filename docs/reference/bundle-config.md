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

Globs compose the configuration. The source and collector jobs live in separate
resource files, so their definitions stay separate from each other and from the
target overrides. See [The dbt job resources](job-resource.md).

## `variables`

Workspace-specific values are bundle variables, supplied at deploy time as
`BUNDLE_VAR_*`:

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
  observability_schema:
    description: Base name for the target-scoped observability schema.
    default: dbt_observability
  observability_volume:
    description: Collector-only managed Volume for canonical dbt archives.
    default: dbt_artifacts
  observability_staging_volume:
    description: Managed Volume for short-lived dbt artifact staging.
    default: dbt_artifacts_staging
  job_duration_warning_seconds:
    description: Native Lakeflow duration-warning threshold.
    default: 900
  notification_emails:
    description: Approved internal notification recipients.
    type: complex
    default: []
  prod_deployer_service_principal_name:
    description: Application ID of the production deployment identity.
  prod_run_as_service_principal_name:
    description: Application ID of the dedicated production dbt identity.
  prod_collector_service_principal_name:
    description: Application ID of the dedicated production collector identity.
```

The `warehouse_id` and `catalog` defaults are deliberately obvious placeholders.
The schema, observability, duration, and notification settings have
non-sensitive operational defaults; the three production identity variables
have no defaults. The schema resource appends `_${bundle.target}` to
`observability_schema`, separating `dev` and `prod`; development mode also
applies its user-specific resource prefix. Supply overrides at deploy time via
`BUNDLE_VAR_*` or a target-specific ignored override file — see
[Configuration values](configuration-values.md).

!!! note "Where the host comes from"
    There is intentionally **no** `workspace.host` in the file. The CLI resolves
    the host from `DATABRICKS_HOST` or your selected profile.

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
      - service_principal_name: ${var.prod_deployer_service_principal_name}
        level: CAN_MANAGE
    resources:
      jobs:
        nyc_taxi_dbt_job:
          run_as:
            service_principal_name: ${var.prod_run_as_service_principal_name}
          permissions:
            - service_principal_name: ${var.prod_collector_service_principal_name}
              level: CAN_VIEW
        dbt_observability_collector_job:
          run_as:
            service_principal_name: ${var.prod_collector_service_principal_name}
      schemas:
        dbt_observability:
          grants:
            - principal: ${var.prod_collector_service_principal_name}
              privileges: [USE_SCHEMA, CREATE_TABLE, SELECT, MODIFY]
            - principal: ${var.prod_run_as_service_principal_name}
              privileges: [USE_SCHEMA]
          lifecycle:
            prevent_destroy: true
      volumes:
        dbt_artifacts:
          grants:
            - principal: ${var.prod_collector_service_principal_name}
              privileges: [READ_VOLUME, WRITE_VOLUME]
          lifecycle:
            prevent_destroy: true
        dbt_artifact_staging:
          grants:
            - principal: ${var.prod_run_as_service_principal_name}
              privileges: [WRITE_VOLUME]
            - principal: ${var.prod_collector_service_principal_name}
              privileges: [READ_VOLUME, WRITE_VOLUME]
          lifecycle:
            prevent_destroy: true
```

| Field | Meaning |
|-------|---------|
| `mode: development` | Prefixes resources with `[dev <user>]`, pauses schedules, marks dev copies |
| `mode: production` | Deploys "for real" to a `root_path` under the deploying principal's home (the CI service principal in automation), with declared permissions |
| `default: true` | Used when `--target` is omitted |
| `${workspace.current_user.userName}` | Resolved at deploy time — no hard-coded user name |
| `permissions.*.service_principal_name` | Classifies the explicit production deployer correctly in the job ACL |
| `jobs.*.run_as` | Executes the source and collector with distinct service principals rather than the deployer |
| source-job `permissions` | Gives only the collector `CAN_VIEW` access to completed source runs |
| staging Volume grants | Gives the source read/write access only to staging and the collector read/write reconciliation access |
| evidence Volume grants | Gives only the collector read/write access to canonical evidence |
| `lifecycle.prevent_destroy` | Blocks ordinary production deletion of the evidence schema and both Volumes |

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

## Included resource files

| File | Resources |
|------|-----------|
| `resources/nyc_taxi.job.yml` | Source dbt job with native health and notifications |
| `resources/dbt_observability_collector.job.yml` | Independent scheduled collector with native health and notifications |
| `resources/observability.infrastructure.yml` | Target-scoped Unity Catalog schema plus staging and evidence managed Volumes |

The collector creates Delta tables and views inside the schema on its first run.
Those objects are runtime evidence rather than separate bundle resources. See
[Observe dbt jobs](../how-to/observe-dbt-jobs.md) for access grants and cleanup.
