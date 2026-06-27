---
icon: lucide/sliders-horizontal
---

# Configuration values

Every workspace-specific value lives **outside** the repo. This page is the
complete contract: what each value is, and where you supply it.

!!! danger "Nothing below is committed"
    No host, warehouse ID, catalog, account ID, username, or token appears in
    git. You provide these at run time through environment variables and GitHub
    Variables. The design rationale is in
    [Keeping secrets out of git](../explanation/security-and-secrets.md).

## Bundle variables (deploy time)

Defined in `databricks.yml`; supplied as `BUNDLE_VAR_<name>`:

| Bundle variable | Supplied locally as | Supplied in CI as | Example |
|-----------------|---------------------|-------------------|---------|
| `warehouse_id` | `BUNDLE_VAR_warehouse_id` | `vars.DATABRICKS_WAREHOUSE_ID` | `<your-warehouse-id>` |
| `catalog` | `BUNDLE_VAR_catalog` | `vars.DATABRICKS_CATALOG` | `<your-catalog>` |
| `schema` | `BUNDLE_VAR_schema` | `vars.DATABRICKS_SCHEMA` | `dbt_nyc_taxi` |

```bash
export BUNDLE_VAR_warehouse_id="<your-warehouse-id>"
export BUNDLE_VAR_catalog="<your-catalog>"
export BUNDLE_VAR_schema="dbt_nyc_taxi"   # optional; default
```

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

!!! tip "Mint a short-lived token instead of a PAT"
    ```bash
    export DBT_ACCESS_TOKEN="$(az account get-access-token \
      --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv)"
    ```
    `2ff814a6-…` is the fixed Azure Databricks programmatic resource ID.

## GitHub repository Variables (CI)

Set under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Fills |
|----------|-------|
| `DATABRICKS_HOST` | CLI host |
| `DATABRICKS_CLIENT_ID` | OIDC service principal (UUID) |
| `DATABRICKS_WAREHOUSE_ID` | `BUNDLE_VAR_warehouse_id` |
| `DATABRICKS_CATALOG` | `BUNDLE_VAR_catalog` |
| `DATABRICKS_SCHEMA` | `BUNDLE_VAR_schema` |

Plus **Environments** named `dev` and `prod`. Setup:
[Set up secretless CI/CD with OIDC](../how-to/set-up-oidc-cicd.md).

## What is never committed to git

None of these appear in any tracked file:

- [ ] Personal access tokens or OAuth client secrets (this repo never uses them at all)
- [ ] The workspace host
- [ ] Warehouse ID and catalog (only `REPLACE_WITH_*` placeholders are committed)
- [ ] Microsoft Entra usernames
- [ ] The Databricks account ID (used only when setting up the account-level OIDC policy)

They live outside git instead — in your shell environment or `~/.databrickscfg`
locally, and in GitHub Variables plus the Databricks federation policy for CI. The
layers that keep them out — bundle variables, env vars, GitHub Variables, OIDC, and
`.gitignore` — are explained in
[Keeping secrets out of git](../explanation/security-and-secrets.md).

!!! note "`schema` is the one committed default"
    Unlike `warehouse_id` and `catalog`, the `schema` variable has a real default
    — `dbt_nyc_taxi` — committed in `databricks.yml`. A schema *name* isn't
    sensitive, and it gives the demo a safe place to build. Override it any time
    with `BUNDLE_VAR_schema`.
