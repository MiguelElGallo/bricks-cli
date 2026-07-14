---
icon: lucide/terminal
---

# CLI commands

This page lists the command contracts used by the repository. Production CI
installs Databricks CLI `1.7.0`; local commands should use the same validated
version. See the official [Databricks CLI commands](https://docs.databricks.com/aws/en/dev-tools/cli/commands).

## Authentication and identity

```text
databricks auth login --host <workspace-url> --profile <profile>
databricks auth token <profile> --output json
databricks auth describe --profile <profile>
databricks current-user me --profile <profile>
```

| Command | Output |
|---------|--------|
| `auth login` | Creates or refreshes a local OAuth U2M profile through browser sign-in |
| `auth token` | Emits a short-lived access token from an OAuth U2M profile; it is not an M2M-secret command |
| `auth describe` | Shows which unified-authentication fields and method were resolved |
| `current-user me` | Returns the workspace identity accepted by the API |

`--profile` can be replaced by `DATABRICKS_CONFIG_PROFILE`. Environment
variables take precedence when they provide a complete authentication method.
See [Authentication support](authentication-support.md) and the official
[unified authentication documentation](https://docs.databricks.com/aws/en/dev-tools/auth/).

## Bundle commands

```text
databricks bundle validate --target dev
databricks bundle plan     --target dev
databricks bundle deploy   --target dev
databricks bundle summary  --target dev --output json
databricks bundle run <resource-key> --target dev
databricks bundle destroy  --target dev
databricks jobs run-now <job-id> --timeout <duration> --output json
```

| Command | Behavior in this repository |
|---------|-----------------------------|
| `validate` | Resolves variables, target overrides, identities, resources, and workspace capabilities |
| `plan` | Shows proposed additions, changes, and deletions without applying them |
| `deploy` | Uploads the project and creates or updates bundle-managed workspace resources |
| `summary` | Returns deployed resource IDs and `workspace.file_path`; CI uses its JSON output for directory ACLs |
| `run nyc_taxi_dbt_job` | Runs the source dbt job and waits for its terminal result |
| `run dbt_observability_collector_job` | Runs one collector sweep and waits for its terminal result |
| `destroy` | Removes a development deployment; production evidence resources have `prevent_destroy` |
| `jobs run-now` | Starts an already-deployed job and returns terminal run metadata; callers must inspect `state.result_state` |

The target name selects bundle settings. It does not select a dbt profile
target. See [Bundle configuration](bundle-config.md).

The protected production workflow invokes `bundle validate`, `bundle deploy`,
and `bundle summary` as the M2M deployer, then invokes both deployed jobs with
`jobs run-now`. Human U2M profiles are for read-only production inspection, not
production deployment or job acceptance. Production destruction is a separate,
reviewed one-time procedure; it is intentionally absent from this everyday
command list.

## Local dbt commands

```text
dbt parse --no-partial-parse --profiles-dir dbt_profiles --target dev
dbt list --profiles-dir dbt_profiles --target dev --output name
dbt build --profiles-dir dbt_profiles --target dev
dbt clean
```

| Command | Workspace connection |
|---------|----------------------|
| `parse` | None when connection-shaped profile variables are present |
| `list` | None for the selectors used by CI |
| `build` | Required; loads the seed, builds the model, and runs tests |
| `clean` | None; deletes local `target/` and `dbt_packages/` |

The deployed dbt task does not use `dbt_profiles/profiles.yml`; Databricks
generates its connection profile from the job resource. See
[dbt project](dbt-project.md).

## Repository quality commands

```bash
ruff check .
ruff format --check .
ty check
pytest
zensical build --clean --strict
```

The first four commands match pull-request CI. The Zensical command matches the
documentation build.

## Output and failures

- Databricks commands accept `--output json` where structured output is needed.
- Bundle commands accept `--profile`/`-p` and `--target`/`-t`.
- A command-level or remote-operation error produces a non-zero exit status.
- `bundle run` also fails when the invoked Lakeflow job finishes unsuccessfully.
- CLI `1.7.0` `jobs run-now` can exit zero after terminal lifecycle even when
  `state.result_state` is not `SUCCESS`; production automation asserts both
  fields explicitly.
- The collector intentionally fails a sweep when any selected attempt fails or
  when work is deferred beyond the batch limit.

## Example

```bash
export DATABRICKS_CONFIG_PROFILE="bricks-demo"
export BUNDLE_VAR_warehouse_id="<warehouse-id>"
export BUNDLE_VAR_catalog="<catalog>"
export BUNDLE_VAR_schema="dbt_nyc_taxi_dev"

databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run nyc_taxi_dbt_job --target dev
databricks bundle run dbt_observability_collector_job --target dev
```
