---
icon: lucide/sliders-horizontal
---

# Configuration values

This page is the complete input contract for bundle deployment, local dbt, and
GitHub Actions. Secret values are never committed.

## Bundle variables

Supply scalar values as `BUNDLE_VAR_<name>`. Variables with no default are
required and make bundle validation fail when they are not supplied.

| Name | Type | Default | Production requirement | Sensitive | Effect |
|------|------|---------|------------------------|-----------|--------|
| `warehouse_id` | string | none | required | workspace-specific | SQL warehouse used by the dbt task |
| `catalog` | string | none | required | workspace-specific | Parent catalog for dbt and observability objects |
| `schema` | string | `dbt_nyc_taxi` | required Secret in the protected workflow; bundle default otherwise | no | Seed/model target schema |
| `observability_schema` | string | `dbt_observability` | optional override | no | Base name; `_<bundle.target>` is appended |
| `observability_staging_volume` | string | `dbt_artifacts_staging` | optional override | no | Producer-writable staging Volume |
| `observability_volume` | string | `dbt_artifacts` | optional override | no | Collector-only evidence Volume |
| `job_duration_warning_seconds` | number | `900` | optional override | no | Source-job duration health threshold |
| `notification_emails` | array | `[]` | optional reviewed override | Personal Data if populated | Native email recipients; empty means no outbound email |
| `prod_deployer_service_principal_name` | string | none | required | workspace-specific | Production deployer Application ID |
| `prod_run_as_service_principal_name` | string | none | required | workspace-specific | Source runner Application ID |
| `prod_collector_service_principal_name` | string | none | required | workspace-specific | Collector Application ID |

The production workflow reads `notification_emails` from the optional
`DATABRICKS_NOTIFICATION_EMAILS` protected environment Secret and falls back to
`[]`. It validates the JSON array and writes it to the ignored target
`variable-overrides.json`; complex values are not accepted through
`BUNDLE_VAR_*`. Store a JSON array such as
`["approved-data-operations@example.com"]`; leave the Secret absent or set it
to `[]` when outbound email is prohibited.

## Databricks CLI authentication

| Name | Local human | Production GitHub | Sensitive |
|------|-------------|-------------------|-----------|
| `DATABRICKS_HOST` | profile or environment | protected `prod` environment Secret | workspace-specific |
| `DATABRICKS_AUTH_TYPE` | inferred by profile; OAuth U2M recommended | committed `oauth-m2m` | no |
| `DATABRICKS_CONFIG_PROFILE` | optional profile selector | unused | no |
| `DATABRICKS_CLIENT_ID` | unused for U2M | protected `prod` environment Secret | workspace-specific identifier |
| `DATABRICKS_CLIENT_SECRET` | unused for U2M | protected `prod` environment Secret | **yes** |

Production uses workspace-level OAuth M2M. `DATABRICKS_ACCOUNT_ID` is not
required for workspace operations. See [Authentication support](authentication-support.md)
and the official [OAuth M2M documentation](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m).

## Local dbt environment

`dbt_profiles/profiles.yml` reads these values for local `dev` and `prod`
targets. The deployed dbt task does not read this profile.

| Name | Required | Default | Format |
|------|----------|---------|--------|
| `DBT_HOST` | yes | none | Hostname without `https://` |
| `DBT_HTTP_PATH` | yes | none | `/sql/1.0/warehouses/<warehouse-id>` |
| `DBT_CATALOG` | yes | none | Unity Catalog catalog name |
| `DBT_SCHEMA` | no | `dbt_nyc_taxi` | Target schema name |
| `DBT_ACCESS_TOKEN` | yes | none | Short-lived token accepted by the SQL warehouse |

The profile uses `method: http` and `threads: 4` for both targets.

## GitHub `prod` environment Secrets

Store production workspace metadata and the OAuth credential under
**Settings → Environments → prod → Environment secrets**. Secret-backed values
are masked before a workflow step runs. After checkout and CLI setup, the
deployment passes only the required values directly into each first-party shell
step; it does not place classified metadata in the job-wide environment.

| Secret | Workflow mapping |
|--------|------------------|
| `DATABRICKS_HOST` | `DATABRICKS_HOST` |
| `DATABRICKS_CLIENT_ID` | M2M client ID and production deployer bundle variable |
| `DATABRICKS_WAREHOUSE_ID` | `BUNDLE_VAR_warehouse_id` |
| `DATABRICKS_CATALOG` | `BUNDLE_VAR_catalog` |
| `DATABRICKS_SCHEMA` | `BUNDLE_VAR_schema` |
| `DATABRICKS_NOTIFICATION_EMAILS` | Optional JSON array written to the ignored production target override; default `[]` |
| `DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME` | Production source runner bundle variable |
| `DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME` | Production collector bundle variable |
| `DATABRICKS_CLIENT_SECRET` | OAuth M2M credential used only by authenticated workspace steps |

GitHub cannot reveal an environment Secret after storage. Keep the approved
host, object identifiers, and three application IDs in the internal change
record used for deployment verification and rotation; do not reconstruct them
from public workflow logs.

PR CI and the documentation workflow receive no Databricks credential.

## Collector task parameters

These are committed notebook `base_parameters`, not operator-supplied runtime
secrets.

| Parameter | Value | Validation |
|-----------|-------|------------|
| `source_job_id` | `${resources.jobs.nyc_taxi_dbt_job.id}` | positive integer |
| `source_task_key` | `dbt_nyc_taxi` | `[A-Za-z0-9_-]+`, at most 128 characters |
| `lookback_days` | `59` | integer from 1 through 59 |
| `max_task_runs_per_sweep` | `100` | integer from 1 through 100 |
| `observability_catalog` | `${var.catalog}` | `[A-Za-z0-9_-]+` |
| `observability_schema` | resolved schema resource name | `[A-Za-z0-9_-]+` |
| `observability_volume` | resolved evidence Volume name | `[A-Za-z0-9_-]+` |
| `observability_staging_volume` | resolved staging Volume name | `[A-Za-z0-9_-]+` |

`workspace_id` is deliberately not configurable. The collector obtains it from
the authenticated Workspace API.

## Example

```bash
export DATABRICKS_CONFIG_PROFILE="bricks-demo"
export BUNDLE_VAR_warehouse_id="<warehouse-id>"
export BUNDLE_VAR_catalog="<catalog>"
export BUNDLE_VAR_schema="dbt_nyc_taxi_dev"
```
