---
icon: lucide/laptop
---

# Run dbt locally

Iterate on models from your machine — running `dbt` directly against your SQL
warehouse — before you deploy the bundle. Nothing workspace-specific is
committed: every value comes from an environment variable.

## Prerequisites

- Python 3.10+ and the [Databricks CLI](../tutorials/install-the-cli.md).
- A SQL warehouse and a Unity Catalog catalog you can write to.
- An authenticated Azure session (`az login`).

## 1. Install the adapter

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` pins the official **`dbt-databricks`** adapter
(`dbt-databricks>=1.8.0,<2.0.0`) — the same range the deployed job installs.

## 2. Point dbt at your workspace

The local profile, `dbt_profiles/profiles.yml`, reads everything from
environment variables, so you set them per shell:

```bash
export DBT_HOST="adb-XXXXXXXXXXXX.NN.azuredatabricks.net"
export DBT_HTTP_PATH="/sql/1.0/warehouses/<your-warehouse-id>"
export DBT_CATALOG="<your-catalog>"
export DBT_SCHEMA="dbt_nyc_taxi"   # optional; this is the default
```

For the token, mint a **short-lived Microsoft Entra ID token** from your `az`
session instead of creating a PAT:

```bash
export DBT_ACCESS_TOKEN="$(az account get-access-token \
  --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d \
  --query accessToken -o tsv)"
```

!!! note "What is that resource ID?"
    `2ff814a6-3304-4ab8-85cb-cd0e6f879c1d` is the fixed **Azure Databricks
    programmatic resource ID** (the same for every Azure tenant). Asking `az` for
    a token scoped to it yields a token your warehouse accepts. It expires in
    about an hour — just re-run the command to refresh it.

## 3. Build and test

```bash
dbt seed --profiles-dir dbt_profiles --target dev
dbt run  --profiles-dir dbt_profiles --target dev
dbt test --profiles-dir dbt_profiles --target dev
```

!!! check
    `dbt run` builds `nyc_taxi_trips` in `<your-catalog>.dbt_nyc_taxi`, and
    `dbt test` confirms the `not_null` assertions. You're iterating against the
    real warehouse without deploying the bundle.

!!! warning "Local targets vs. the deployed job"
    Locally you pass `--target dev` because `profiles.yml` defines `dev`/`prod`
    targets. The **deployed job does not** — Databricks generates its own profile
    with a single target, so its commands omit `--target`. See
    [How dbt connects to Databricks](../explanation/how-dbt-connects.md).

## Prefer interactive setup?

Optional: `dbt init` reads `profile_template.yml` to prompt for the host,
warehouse HTTP path, catalog, and schema, then writes a profile to
`~/.dbt/profiles.yml` (outside the repo). It also prompts for a **token**.

!!! warning "Use a short-lived token here too"
    The `dbt-databricks` adapter's `token` field accepts any bearer token, so
    paste a **short-lived Microsoft Entra token** — the same value from
    `az account get-access-token …` in step 2 — rather than creating a long-lived
    personal access token (PAT). Whatever you enter is written to
    `~/.dbt/profiles.yml`, never to the repo, and an Entra token expires on its
    own in about an hour.

## Related

- [Add a dbt model](add-a-model.md)
- Reference: [Configuration values](../reference/configuration-values.md)
- Explanation: [How dbt connects to Databricks](../explanation/how-dbt-connects.md)
