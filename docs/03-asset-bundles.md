# 03 – Declarative Automation Bundles (DABs)

> **Is a bundle still the way to go?** Yes. This page is the long answer.

## What a bundle is

A **Declarative Automation Bundle** (the feature historically called *Databricks
Asset Bundles*) expresses a "data/AI/analytics project as code": your source plus
the Databricks resources that run it (jobs, pipelines, …), described in YAML and
deployed with `databricks bundle`. It is the **first‑party, recommended** unit of
deployment for Databricks and is built into the CLI — nothing extra to install.

## Direct deployment: no Terraform required

Historically a bundle deploy delegated to an embedded Terraform provider. The
latest CLI ships a **direct deployment** engine that calls the Databricks APIs
itself, removing the Terraform dependency. That is exactly the promise in this
repo's name: *"the new Databricks CLI that does not need Terraform."*

Practical effects:

- No Terraform binary, provider download, or `.tf` state to manage.
- `databricks bundle deploy` / `plan` / `destroy` operate directly on the APIs.
- Infra provisioning that genuinely needs Terraform (VNets, workspaces themselves)
  is still Terraform's job — bundles deploy **code and workspace resources**, not
  the cloud account underneath.

## Why bundles over rolling your own

| Concern | Bundles give you |
|--------|------------------|
| Reproducibility | One declarative source of truth, versioned in Git |
| Environments | `targets` (dev/prod) with per‑target overrides |
| Safety | `development` mode isolates and prefixes resources, pauses schedules |
| CI/CD | `validate` → `deploy` → `run` map cleanly onto pipeline stages |
| Drift / cleanup | `summary`, `plan`, and `destroy` |

## Anatomy of *this* bundle

`databricks.yml` is the root:

```yaml
bundle:
  name: bricks_cli_dbt
  uuid: …

include:
  - resources/*.yml        # pull in resource definitions

targets:
  dev:  { mode: development, default: true, workspace: { host: … } }
  prod: { mode: production,  workspace: { host: …, root_path: … }, permissions: [ … ] }
```

- **`bundle`** — name (and a uuid) that identify the project.
- **`include`** — globs that compose the config; here the job lives in
  `resources/nyc_taxi.job.yml` so resources stay tidy and separate from targets.
- **`targets`** — named environments. `dev` is the default; `prod` deploys to a
  fixed `root_path` and grants explicit permissions.

The single resource is a **job** that runs dbt on **serverless** compute — see
[docs/04](04-dbt-on-databricks.md) for the task itself.

## Deployment modes (why `dev` is safe)

`mode: development` (our default `dev` target):

- prefixes deployed resources with `[dev <your-username>]`,
- **pauses** schedules/triggers so nothing fires while you iterate,
- marks resources as development copies so they're easy to find and clean up.

`mode: production` (the `prod` target) deploys "for real" to a single, well‑known
`root_path` and applies the permissions you declare.

## The commands you'll actually run

```bash
databricks bundle validate --target dev      # resolve + type‑check the config
databricks bundle plan     --target dev      # preview changes (optional)
databricks bundle deploy   --target dev      # upload files + create/update resources
databricks bundle run nyc_taxi_dbt_job -t dev # run the job now
databricks bundle summary  --target dev      # what's deployed?
databricks bundle destroy  --target dev      # tear it down
```

## Sources

- Databricks CLI bundle help (`databricks bundle --help`) — *"Declarative
  Automation Bundles let you express data/AI/analytics projects as code."*
- Microsoft Learn: [Declarative Automation Bundles](https://learn.microsoft.com/azure/databricks/dev-tools/bundles/)
  and the [feature release notes](https://learn.microsoft.com/azure/databricks/release-notes/dev-tools/bundles)
  (direct deployment, GA).
- The CLI's own `dbt-sql` bundle template, which this project is modelled on.

---
Next: [04 – dbt on Databricks](04-dbt-on-databricks.md).
