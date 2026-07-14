---
icon: lucide/sliders-horizontal
---

# Configuration values

Every workspace-specific value lives **outside** the repo. This page is the
complete contract: what each value is, and where you supply it.

You provide these at run time through environment variables (locally) and GitHub
Variables (in CI). For the design rationale, see
[Keeping secrets out of git](../explanation/security-and-secrets.md).

## Bundle variables (deploy time)

Defined in `databricks.yml`; supplied as `BUNDLE_VAR_<name>`:

| Bundle variable | Default | Meaning |
|-----------------|---------|---------|
| `warehouse_id` | `REPLACE_WITH_YOUR_WAREHOUSE_ID` | SQL warehouse used by dbt |
| `catalog` | `REPLACE_WITH_YOUR_CATALOG` | Catalog for dbt and observability objects |
| `schema` | `dbt_nyc_taxi` | dbt seed/model target schema |
| `observability_schema` | `dbt_observability` | Base schema; the target suffix and any development-mode resource prefix are applied |
| `observability_staging_volume` | `dbt_artifacts_staging` | Managed Volume for short-lived per-attempt dbt target output |
| `observability_volume` | `dbt_artifacts` | Collector-only managed Volume for content-addressed canonical archives |
| `job_duration_warning_seconds` | `900` | Native `RUN_DURATION_SECONDS` threshold |
| `notification_emails` | `[]` | Approved internal recipients; complex array |
| `prod_deployer_service_principal_name` | required for `prod` | Application ID of the production deployment identity used in the job ACL |
| `prod_run_as_service_principal_name` | required for `prod` | Application ID of the dedicated production dbt-runner identity |
| `prod_collector_service_principal_name` | required for `prod` | Application ID of the dedicated production collector identity |

```bash
export BUNDLE_VAR_warehouse_id="<your-warehouse-id>"
export BUNDLE_VAR_catalog="<your-catalog>"
export BUNDLE_VAR_schema="dbt_nyc_taxi_dev"
export BUNDLE_VAR_observability_schema="dbt_observability"
export BUNDLE_VAR_observability_staging_volume="dbt_artifacts_staging"
export BUNDLE_VAR_observability_volume="dbt_artifacts"
export BUNDLE_VAR_job_duration_warning_seconds="900"
export BUNDLE_VAR_prod_deployer_service_principal_name="<deployment-service-principal-application-id>" # prod only
export BUNDLE_VAR_prod_run_as_service_principal_name="<dbt-service-principal-application-id>" # prod only
export BUNDLE_VAR_prod_collector_service_principal_name="<collector-service-principal-application-id>" # prod only
```

`notification_emails` is complex. For local deployment, use the ignored
`.databricks/bundle/<target>/variable-overrides.json` file:

```json
{
  "notification_emails": []
}
```

Keep it empty when outbound email is prohibited. If enabled, use only an
approved internal distribution list, never a personal address. The existing CI
workflows use the committed empty default; adding notification recipients to CI
requires an explicit, reviewed complex-variable mapping.

## CLI authentication

| Value | Where | Notes |
|-------|-------|-------|
| `DATABRICKS_HOST` | env var or profile | Workspace URL, e.g. `https://adb-XXXXXXXXXXXX.NN.azuredatabricks.net` |
| `DATABRICKS_AUTH_TYPE` | env var or profile | `azure-cli` locally; `github-oidc` in CI |
| `DATABRICKS_CLIENT_ID` | GitHub Variable | Service principal **Application ID** (UUID); not a secret |
| `DATABRICKS_CONFIG_PROFILE` | env var | Alternative to `-p/--profile` |

Locally, a `~/.databrickscfg` profile is the convenient option:

```ini
[bricks-demo]
host      = https://adb-XXXXXXXXXXXX.NN.azuredatabricks.net
auth_type = azure-cli
```

## Local dbt environment variables

Read by `dbt_profiles/profiles.yml` for **local** runs only (the deployed job
does not use this file):

| Env var | Meaning | Example |
|---------|---------|---------|
| `DBT_HOST` | Workspace host (no scheme) | `adb-XXXXXXXXXXXX.NN.azuredatabricks.net` |
| `DBT_HTTP_PATH` | SQL warehouse HTTP path | `/sql/1.0/warehouses/<id>` |
| `DBT_CATALOG` | Unity Catalog catalog | `<your-catalog>` |
| `DBT_SCHEMA` | Target schema (default `dbt_nyc_taxi`) | `dbt_nyc_taxi` |
| `DBT_ACCESS_TOKEN` | Short-lived token | from `az account get-access-token …` |

!!! tip "Where `DBT_ACCESS_TOKEN` comes from"
    Mint a short-lived token with the Azure CLI rather than a PAT — the one-liner
    is in [Run dbt locally](../how-to/run-dbt-locally.md).

## GitHub repository Variables (CI)

Set under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Fills |
|----------|-------|
| `DATABRICKS_HOST` | CLI host |
| `DATABRICKS_CLIENT_ID` | OIDC deployment service principal (UUID); also fills the prod deployer ACL variable |
| `DATABRICKS_WAREHOUSE_ID` | `BUNDLE_VAR_warehouse_id` |
| `DATABRICKS_CATALOG` | `BUNDLE_VAR_catalog` |
| `DATABRICKS_SCHEMA` | `BUNDLE_VAR_schema` |
| `DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME` | required production dbt-runner identity |
| `DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME` | required production collector identity |

Plus **Environments** named `dev` and `prod`. Setup:
[Set up secretless CI/CD with OIDC](../how-to/set-up-oidc-cicd.md).

!!! note "`schema` has a committed default"
    Unlike `warehouse_id` and `catalog`, the `schema` variable has a real default
    — `dbt_nyc_taxi` — committed in `databricks.yml`. A schema *name* isn't
    sensitive, and it gives the project a safe place to build. Override it any
    time with `BUNDLE_VAR_schema`. In CI, both workflows always pass
    `BUNDLE_VAR_schema` from `vars.DATABRICKS_SCHEMA`, so set that Variable — an
    unset Variable passes an empty string and overrides the default.

## Fixed runtime and privacy settings

These values are committed rather than supplied at deployment time:

| Setting | Value |
|---------|-------|
| dbt Core | `1.11.11` |
| `dbt-databricks` | `1.12.2` |
| Databricks SDK for Python | `0.117.0` |
| dbt anonymous usage statistics | disabled in `dbt_project.yml` |

The source writes dbt JSON artifacts to the staging Volume with `--target-path`.
The collector reads `manifest.json` and `run_results.json`, creates a
deterministic two-file tar in the evidence Volume, and exposes only allowlisted
operational fields through curated views. Capture cleanup removes reconciled
staging leaves; it does not delete durable evidence.
