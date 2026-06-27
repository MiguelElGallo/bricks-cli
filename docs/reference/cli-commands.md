---
icon: lucide/terminal
---

# CLI commands

Source of truth: [github.com/databricks/cli](https://github.com/databricks/cli).
This demo was built and verified with **Databricks CLI v1.5.0**.

## Command groups used here

`databricks --help` groups commands by area. The ones this demo touches:

| Group | Example | Used for |
|-------|---------|----------|
| `bundle` | `databricks bundle deploy` | Deploy this project (the headline) |
| `current-user` | `databricks current-user me` | Confirm who you're authenticated as |
| `warehouses` | `databricks warehouses list` | Find the SQL warehouse ID for dbt |
| `catalogs` | `databricks catalogs list` | Pick the Unity Catalog target |
| `api` | `databricks api post /api/2.0/sql/statements` | Ad-hoc REST calls (e.g. query a table) |

## `databricks bundle` subcommands

`databricks bundle --help` lists the subcommands that power this repo:

| Subcommand | Purpose |
|------------|---------|
| `validate` | Resolve and type-check the bundle config for a target |
| `plan` | Preview what a deploy would change |
| `deploy` | Upload files and create/update resources (direct deployment) |
| `run` | Run a job/pipeline defined in the bundle |
| `summary` | Show what's deployed |
| `destroy` | Tear down deployed resources |
| `init` | Scaffold a new bundle from a template (e.g. `dbt-sql`) |
| `generate` | Import an existing job/pipeline into bundle YAML |

A typical local cycle (the `-p bricks-demo` profile carries your host and
`azure-cli` auth — see [Connect to Databricks](../tutorials/connect-to-databricks.md)):

```bash
databricks bundle validate -t dev -p bricks-demo   # resolve + type-check
databricks bundle plan     -t dev -p bricks-demo   # preview changes (optional)
databricks bundle deploy   -t dev -p bricks-demo   # upload files + create/update resources
databricks bundle run nyc_taxi_dbt_job -t dev -p bricks-demo   # run the job now
databricks bundle summary  -t dev -p bricks-demo   # what's deployed?
databricks bundle destroy  -t dev -p bricks-demo   # tear it down
```

## dbt commands (run by the job and locally)

| Command | Purpose |
|---------|---------|
| `dbt seed` | Load the seed CSV into the warehouse |
| `dbt run` | Build the model(s) — here, the `nyc_taxi_trips` table |
| `dbt test` | Run data tests (e.g. `not_null`) after the build |
| `dbt build` | `seed` + `run` + `test` in dependency order |
| `dbt init` | Create a local profile from `profile_template.yml` |

!!! note "`--target` locally, but not in the job"
    Local runs use `--profiles-dir dbt_profiles --target dev`. The **deployed
    job omits `--target`** because Databricks generates the profile from the dbt
    task's `warehouse_id` / `catalog` / `schema`. See
    [How dbt connects to Databricks](../explanation/how-dbt-connects.md).

## Global flags worth knowing

| Flag | Effect |
|------|--------|
| `-t`, `--target` | Select a bundle target (`dev`, `prod`) |
| `-p`, `--profile` | Select a `~/.databrickscfg` profile |
| `-o json` | Machine-readable output |
| `--debug` | Print the underlying API calls |

## Installing in CI

Use the first-party action, pinned for reproducibility:

```yaml
- uses: databricks/setup-cli@v1.5.0
  with:
    version: 1.5.0
```

!!! info "Stability"
    The CLI follows **Semantic Versioning**; commands and flags are stable within
    a major version. Features marked *Beta* / *Private Preview* or under
    `databricks experimental` may change in a minor release — pinning an exact
    version keeps deployments reproducible.
