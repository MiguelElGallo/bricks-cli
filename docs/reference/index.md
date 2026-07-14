---
icon: lucide/book-open
---

# Reference

This section is the exact contract for the repository as committed: names,
versions, inputs, defaults, permissions, paths, schemas, states, and errors.
Use the [tutorial](../tutorials/index.md) to learn the project and the
[how-to guides](../how-to/index.md) to complete an operational task.

!!! info "Source of truth"
    These pages mirror `databricks.yml`, `resources/`, `.github/workflows/`,
    `dbt_project.yml`, and `src/observability/`. If prose and executable source
    ever disagree, the executable source wins and the reference needs updating.

## Project and delivery

| Page | Contract |
|------|----------|
| [CLI commands](cli-commands.md) | Commands used by this repository |
| [dbt project](dbt-project.md) | dbt paths, profile, seed, model, and tests |
| [Bundle configuration](bundle-config.md) | Bundle identity, targets, variables, and resources |
| [Configuration values](configuration-values.md) | Every runtime input and where it is supplied |
| [GitHub workflows](workflows.md) | CI, production deployment, and Pages publication |
| [Project layout](project-layout.md) | Repository paths and ownership |
| [Runtime versions](runtime-versions.md) | Pinned CLI, Python, dbt, SDK, and docs versions |

## Jobs and evidence

| Page | Contract |
|------|----------|
| [Source dbt job](source-job.md) | Schedule, dbt task, retry, staging, and notifications |
| [Artifact collector job](collector-job.md) | Schedule, inputs, batching, outputs, and failure behavior |
| [Observability objects](observability-objects.md) | Three restricted tables and five curated views |
| [AttemptKey](attempt-key.md) | Six-field identity used everywhere |
| [Capture states](capture-states.md) | Capture, cleanup, and combined evidence states |
| [Evidence layout](evidence-layout.md) | Staging, canonical archive, quarantine, and limits |
| [Error codes](error-codes.md) | Full allowlisted collector error dictionary |

## Security

| Page | Contract |
|------|----------|
| [Authentication support](authentication-support.md) | Active and unavailable authentication methods |
| [Permissions](permissions.md) | Deployer, runner, collector, and operator access |

Use the [Glossary](glossary.md) for repository-specific terminology.

## Compatibility URLs

Two unnaved pages preserve previously published links without duplicating a
current contract:

- [Former combined job-resource page](job-resource.md)
- [Former GitHub OIDC setup page](../how-to/set-up-oidc-cicd.md)
