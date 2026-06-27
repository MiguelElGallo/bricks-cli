# bricks-cli — deploy a dbt project to Databricks with the new Databricks CLI

A small, end-to-end reference for deploying a dbt project to Azure Databricks
using the latest **Databricks CLI** and **Declarative Automation Bundles (DABs)** —
the bundle's *direct deployment* engine, so **no Terraform is required**.

The dbt scope is deliberately tiny so the deployment mechanics stay front and
centre: **one seed → one table.** A 100‑row extract of the public
`samples.nyctaxi.trips` table is committed as a dbt seed and materialized into a
Delta table by a single dbt model.

📖 **Documentation site:** <https://miguelelgallo.github.io/bricks-cli/> —
structured with [Diátaxis](https://diataxis.fr/) (Tutorial · How‑to · Reference ·
Explanation) and built with [Zensical](https://zensical.org/). The Markdown
sources live in [`docs/`](docs/).

```mermaid
flowchart LR
    subgraph repo["This repo (a Declarative Automation Bundle)"]
        seed["seed CSV<br/>nyc_taxi_trips_seed"]
        model["model (table)<br/>nyc_taxi_trips"]
        job["resources/*.job.yml<br/>serverless dbt job"]
        seed --> model
    end
    cli["Databricks CLI v1.5.0<br/>bundle validate / deploy / run"]
    repo -->|databricks bundle deploy| cli
    cli --> ws["Azure Databricks workspace"]
    ws --> wh["Serverless SQL warehouse"]
    job -->|dbt seed/run/test| wh
    wh --> tbl["&lt;catalog&gt;.dbt_nyc_taxi.nyc_taxi_trips"]
```

## Is a bundle still the way to go? (the research question)

**Yes.** Declarative Automation Bundles are the first‑party, recommended way to
package and deploy Databricks projects as code. The important 2025–2026 change is
that the latest CLI ships a **direct deployment** engine, so a bundle deploy no
longer shells out to Terraform — exactly what this repo's name asks for. Details
and sources are in
[Why Declarative Automation Bundles](docs/explanation/why-asset-bundles.md).

## Repository layout

```
.
├── databricks.yml                  # bundle definition + dev/prod targets
├── resources/
│   └── nyc_taxi.job.yml             # serverless job that runs the dbt task
├── dbt_project.yml                 # dbt project (paths under src/)
├── dbt_profiles/
│   └── profiles.yml                # dbt profile for local runs (env‑var based)
├── profile_template.yml            # prompts for `dbt init` (local profile)
├── requirements-dev.txt            # dbt-databricks adapter (local dev)
├── requirements-docs.txt           # Zensical (builds the docs site)
├── zensical.toml                   # documentation site configuration
├── src/
│   ├── seeds/nyc_taxi/             # the seed CSV + its properties
│   └── models/nyc_taxi/           # the single table model + tests
├── .github/workflows/             # OIDC CI + deploy, and docs → Pages
├── docs/                           # documentation site sources (Diátaxis)
└── .agents/skills/                # installed dbt agent skills
```

## Quickstart

Prerequisites: the Databricks CLI (see
[Install the CLI](docs/tutorials/install-the-cli.md)) and an authenticated
session (see [Connect to Databricks](docs/tutorials/connect-to-databricks.md)).
Supply workspace‑specific values as env vars (locally) or GitHub Variables (in
CI); see
[Configuration values](docs/reference/configuration-values.md). Then, from the
repo root — these commands authenticate from the env vars above, so they need no
`-p` profile flag:

```bash
export DATABRICKS_HOST="https://adb-XXXXXXXXXXXX.NN.azuredatabricks.net"
export DATABRICKS_AUTH_TYPE="azure-cli"   # reuse your `az login` session
export BUNDLE_VAR_warehouse_id="<your-warehouse-id>"
export BUNDLE_VAR_catalog="<your-catalog>"

databricks bundle validate --target dev   # check the config
databricks bundle deploy   --target dev   # upload + create the job (no Terraform)
databricks bundle run nyc_taxi_dbt_job --target dev   # seed → table → test
```

Want to iterate on the models locally first? See
[Run dbt locally](docs/how-to/run-dbt-locally.md).

## Documentation

The full guide is a [Zensical](https://zensical.org/) site published to GitHub
Pages and organized with the [Diátaxis](https://diataxis.fr/) framework. It's
written against [databricks/cli](https://github.com/databricks/cli) concepts.

👉 **<https://miguelelgallo.github.io/bricks-cli/>**

| Section | What it covers |
|---------|----------------|
| [Tutorial – User Guide](docs/tutorials/index.md) | A guided, FastAPI‑style path from zero to a deployed, running dbt job |
| [How‑to guides](docs/how-to/index.md) | Run dbt locally, add a model, set up OIDC CI/CD, deploy to prod |
| [Reference](docs/reference/index.md) | CLI commands, bundle config, the dbt job resource, every config value, layout |
| [Explanation](docs/explanation/index.md) | Why bundles, the auth model, how dbt connects, keeping secrets out of git |

Build the site locally with `pip install -r requirements-docs.txt && zensical serve`.

## dbt agent skills

The official [dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills)
are installed under `.agents/skills/` so AI agents working in this repo can use
them. See
[Project layout → dbt agent skills](docs/reference/project-layout.md#dbt-agent-skills).
