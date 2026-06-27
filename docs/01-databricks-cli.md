# 01 – The Databricks CLI

Source of truth: [github.com/databricks/cli](https://github.com/databricks/cli).

## What it is

The Databricks CLI is a single, **dependency‑free binary** that talks to the
Databricks REST APIs and drives Declarative Automation Bundles. The same binary
works across clouds (Azure, AWS, GCP); this repo targets **Azure Databricks**.

This demo was built and verified with **Databricks CLI v1.5.0**.

> Note on names: the older "legacy" Databricks CLI was a Python package
> (`pip install databricks-cli`). The current CLI is the Go binary from
> `databricks/cli`. Use the binary — that is what bundles require.

## Install the latest version

Pick one (all give you the same binary):

```bash
# Homebrew (macOS/Linux) — maintained tap
brew tap databricks/tap
brew install databricks

# Or the official install script (installs the latest release)
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh

# Or download a specific release binary (what this repo pins)
#   https://github.com/databricks/cli/releases/tag/v1.5.0
```

Verify:

```bash
databricks version
# Databricks CLI v1.5.0
```

In CI, use the first‑party action instead (see [docs/05](05-deploy-and-run.md)):

```yaml
- uses: databricks/setup-cli@v1.5.0
  with:
    version: 1.5.0
```

## Command groups you'll meet here

`databricks --help` groups commands by area. The ones this demo touches:

| Group | Example | Used for |
|-------|---------|----------|
| `bundle` | `databricks bundle deploy` | Deploy this project (the headline) |
| `current-user` | `databricks current-user me` | Confirm who you're authenticated as |
| `warehouses` | `databricks warehouses list` | Find the SQL warehouse id for dbt |
| `catalogs` | `databricks catalogs list` | Pick the Unity Catalog target |
| `api` | `databricks api post /api/2.0/sql/statements` | Ad‑hoc REST calls (e.g. query a table) |

## The `bundle` command

`databricks bundle --help` lists the subcommands that power this repo:

| Subcommand | Purpose |
|------------|---------|
| `validate` | Type‑check and resolve the bundle config for a target |
| `deploy` | Upload files and create/update resources (direct deployment) |
| `plan` | Preview what a deploy would change |
| `run` | Run a job/pipeline defined in the bundle |
| `summary` | Show what's deployed |
| `destroy` | Tear down deployed resources |
| `init` | Scaffold a new bundle from a template (e.g. `dbt-sql`) |
| `generate` | Import an existing job/pipeline into bundle YAML |

## Configuration & output

- **Profiles** live in `~/.databrickscfg`; select one with `-p/--profile`
  (see [docs/02](02-authentication.md)).
- **Target** selects a bundle environment with `-t/--target` (e.g. `dev`, `prod`).
- **Output**: add `-o json` to any command for machine‑readable output.
- **Debugging**: add `--debug` to see the underlying API calls.

## Stability & versioning (worth knowing before you pin)

Per the CLI's stability policy, it follows **Semantic Versioning**. Commands and
flags are **stable within a major version**; features marked *Beta*/*Private
Preview* or under `databricks experimental` may change in a minor release. Pinning
an exact version (as the CI here does) keeps deployments reproducible.

---
Next: [02 – Authentication](02-authentication.md).
