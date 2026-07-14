---
icon: lucide/package
---

# Bundle configuration

`databricks.yml` is the root configuration for the Declarative Automation
Bundle. The validated CLI is `1.7.0`; field semantics follow the official
[bundle configuration reference](https://docs.databricks.com/aws/en/dev-tools/bundles/reference).

## Bundle identity

```yaml
bundle:
  name: bricks_cli_dbt
  uuid: b678d035-88c4-470e-8bf4-2e81accd95f5

include:
  - resources/*.yml
```

| Field | Value | Effect |
|-------|-------|--------|
| `bundle.name` | `bricks_cli_dbt` | Stable project name used in deployment paths and resource metadata |
| `bundle.uuid` | `b678d035-88c4-470e-8bf4-2e81accd95f5` | Stable bundle identity |
| `include` | `resources/*.yml` | Merges both jobs and Unity Catalog infrastructure into the bundle graph |

## Variables

The bundle declares eleven variables. Scalar values can be supplied as
`BUNDLE_VAR_<name>`. The complex `notification_emails` value must use
`.databricks/bundle/<target>/variable-overrides.json` and is normally left at
its empty committed default.

| Variable | Type | Default | Required in production |
|----------|------|---------|------------------------|
| `warehouse_id` | string | none | yes |
| `catalog` | string | none | yes |
| `schema` | string | `dbt_nyc_taxi` | no |
| `observability_schema` | string | `dbt_observability` | no |
| `observability_volume` | string | `dbt_artifacts` | no |
| `observability_staging_volume` | string | `dbt_artifacts_staging` | no |
| `job_duration_warning_seconds` | number | `900` | no |
| `notification_emails` | complex array | `[]` | no |
| `prod_run_as_service_principal_name` | string | none | yes |
| `prod_collector_service_principal_name` | string | none | yes |
| `prod_deployer_service_principal_name` | string | none | yes |

The three service-principal variables are set to `unused-in-dev` by the `dev`
target because development does not apply production `run_as` overrides.
See [Configuration values](configuration-values.md) for sources and sensitivity.

## Targets

```text
dev  = mode: development, default: true
prod = mode: production, fixed root_path, explicit identities and grants
```

| Property | `dev` | `prod` |
|----------|-------|--------|
| Default target | yes | no |
| Resource prefix | `[dev <current-user>]` | none |
| Source trigger | paused by development mode | active |
| Collector schedule | paused | explicitly `UNPAUSED` |
| `run_as` | deploying user | dedicated runner and collector service principals |
| Root path | development-mode default | `/Workspace/Users/${var.prod_deployer_service_principal_name}/.bundle/${bundle.name}/${bundle.target}` |
| Evidence deletion guard | none | `prevent_destroy: true` on schema and both Volumes |

Development mode isolates workspace resource names and schedules, not the dbt
catalog or schema. Supply a separate `schema` value for development data. See
the official [deployment modes](https://docs.databricks.com/aws/en/dev-tools/bundles/deployment-modes).

The production root is stable across caller identities, but production mutation
still belongs exclusively to the protected deployer-M2M workflow. Human U2M is
for read-only inspection and administration, not an alternate deployment path.

## Production overrides

| Resource | Override |
|----------|----------|
| Bundle | Deployer service principal receives `CAN_MANAGE` |
| Source job | Runs as the runner; collector receives `CAN_VIEW` |
| Collector job | Runs as the collector; schedule becomes `UNPAUSED` |
| Observability schema | Collector receives `USE_SCHEMA`, `CREATE_TABLE`, `SELECT`, `MODIFY`; runner receives `USE_SCHEMA` |
| Evidence Volume | Collector receives `READ_VOLUME`, `WRITE_VOLUME` |
| Staging Volume | Runner and collector receive `READ_VOLUME`, `WRITE_VOLUME` |

Parent-catalog access, target dbt-schema privileges, SQL warehouse access,
service-principal-use permissions, optional system-table access, and deployed
file ACLs are external prerequisites. See [Permissions](permissions.md).

## Resource graph

| File | Bundle resources |
|------|------------------|
| `resources/nyc_taxi.job.yml` | `jobs.nyc_taxi_dbt_job` |
| `resources/dbt_observability_collector.job.yml` | `jobs.dbt_observability_collector_job` |
| `resources/observability.infrastructure.yml` | `schemas.dbt_observability`, `volumes.dbt_artifact_staging`, `volumes.dbt_artifacts` |

The collector creates its Delta tables and views at runtime; those are not
bundle resources. See [Observability objects](observability-objects.md).

## Host resolution

There is no committed `workspace.host`. The CLI resolves the host from a
complete unified-authentication environment or a selected profile. This keeps a
specific workspace URL out of source control.

## Example

```bash
export BUNDLE_VAR_warehouse_id="<warehouse-id>"
export BUNDLE_VAR_catalog="<catalog>"
export BUNDLE_VAR_schema="dbt_nyc_taxi_dev"

databricks bundle validate --target dev --profile bricks-demo
```
