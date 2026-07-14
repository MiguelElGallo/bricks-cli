---
icon: lucide/database
hide:
  - navigation
---

# bricks-cli

A small, end-to-end reference for deploying a [dbt](https://www.getdbt.com/)
project to **Azure Databricks** using the latest **Databricks CLI** and
**Declarative Automation Bundles (DABs)** — the bundle's *direct deployment*
engine, so **no Terraform is required**.

The dbt scope is deliberately tiny so the deployment mechanics stay front and
centre: **one seed → one table.** A 100-row extract of the public
`samples.nyctaxi.trips` table is committed as a dbt seed and materialized into a
Delta table by a single dbt model.

It also includes a **Databricks-only observability path** for regulated
environments: dbt stages two JSON artifacts in a governed Unity Catalog Volume,
an independent collector creates a deterministic content-addressed archive, and
operators use sanitized Delta health views. dbt anonymous usage reporting is
disabled and no external telemetry platform or cloud-specific monitoring
service is required.

```mermaid
flowchart LR
    subgraph repo["This repo (a Declarative Automation Bundle)"]
        seed["seed CSV<br/>nyc_taxi_trips_seed"]
        model["model (table)<br/>nyc_taxi_trips"]
        job["source dbt job"]
        seed --> model
    end
    cli["Databricks CLI<br/>bundle validate / deploy / run"]
    repo -->|databricks bundle deploy| cli
    cli --> ws["Databricks workspace"]
    ws --> wh["Serverless SQL warehouse"]
    job -->|"one dbt build"| wh
    wh --> tbl["&lt;catalog&gt;.dbt_nyc_taxi.nyc_taxi_trips"]
    job -->|"--target-path"| staging["staging Volume<br/>manifest + run results"]
    schedule["every 15 minutes"] --> collector["independent collector job"]
    collector -->|"Jobs API: completed runs"| job
    staging --> collector
    collector --> evidence["canonical archive + sanitized Delta health views"]
    system["system.lakeflow"] --> evidence
```

!!! tip "New here? Start with the tutorial."
    The [Tutorial - User Guide](tutorials/index.md) walks you from an empty
    terminal to a dbt job running on Databricks, one small step at a time.

## Find your way around

This documentation follows the [Diátaxis](https://diataxis.fr/) framework. The
four sections answer four different questions, so pick the one that matches what
you need right now.

<div class="grid cards" markdown>

-   :lucide-graduation-cap: **Tutorial**

    ---

    *Learning-oriented.* A guided, hands-on lesson that takes you from zero to a
    deployed, running dbt job. Start here if you're new.

    [:lucide-arrow-right: Tutorial - User Guide](tutorials/index.md)

-   :lucide-wrench: **How-to guides**

    ---

    *Task-oriented.* Short recipes for specific jobs — run dbt locally, observe
    jobs, set up CI/CD, deploy to production.

    [:lucide-arrow-right: How-to guides](how-to/index.md)

-   :lucide-book-open: **Reference**

    ---

    *Information-oriented.* The dry facts: CLI commands, bundle fields, the dbt
    job resource, every configuration value, and the project layout.

    [:lucide-arrow-right: Reference](reference/index.md)

-   :lucide-lightbulb: **Explanation**

    ---

    *Understanding-oriented.* The "why" behind the design: bundles, the
    authentication model, how dbt connects, and keeping secrets out of git.

    [:lucide-arrow-right: Explanation](explanation/index.md)

</div>

## Is a bundle still the way to go?

**Yes.** Declarative Automation Bundles are the first-party, recommended way to
package and deploy Databricks projects as code. The important 2025–2026 change is
that the latest CLI ships a **direct deployment** engine, so a bundle deploy no
longer shells out to Terraform — exactly what this repo's name asks for. The full
answer, with sources, is in
[Why Declarative Automation Bundles](explanation/why-asset-bundles.md).

## Observe the job without another platform

The source job runs one selected `dbt build` and reports that dbt result
directly. An independent collector job runs every 15 minutes, scans completed
source runs through the Jobs API, and reconciles each matching staged attempt.
The source writes `manifest.json` and `run_results.json` with `--target-path`;
the collector creates a deterministic two-file archive keyed by the full
attempt identity, publishes sanitized facts, and cleans staging separately.
Start with
[Observe dbt jobs](how-to/observe-dbt-jobs.md) for permissions, health queries,
source/collector verification, and cleanup.
