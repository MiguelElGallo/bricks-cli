---
icon: lucide/workflow
---

# GitHub workflows

Three workflows separate untrusted pull-request checks, protected production
deployment, and documentation publication.

Third-party actions are pinned to full commit SHAs, with the reviewed release
tag retained in a comment. This is the immutable form recommended for
security-sensitive workflows.

## Workflow matrix

| File | Trigger | Databricks credential | Environment | Concurrency |
|------|---------|------------------------|-------------|-------------|
| `.github/workflows/ci.yml` | Pull request to `main` | none | none | `ci-${{ github.ref }}` |
| `.github/workflows/deploy.yml` | Push to `main`; manual `deploy` or `freeze` | OAuth M2M secret | protected `prod` | `deploy-prod` |
| `.github/workflows/docs.yml` | Relevant push to `main`; manual | none | `github-pages` for deployment | `pages` |

## Pull-request CI

```text
install requirements-dev.txt
→ ruff check
→ ruff format --check
→ ty check
→ pytest
→ install requirements-docs.txt
→ zensical build --clean --strict
→ dbt parse (offline)
→ dbt list (offline)
```

The job has `contents: read` only and `DO_NOT_TRACK=1`. Connection-shaped
`DBT_*` placeholders satisfy profile rendering, but neither dbt command contacts
Databricks. The strict documentation build runs in the same PR job. Bundle
validation is intentionally deferred because it is
workspace-aware and would expose a reusable credential to pull-request code.

## Protected production operations

Pushes to `main` always select `deploy`. A manual dispatch requires one explicit
choice:

| Operation | Effect |
|---|---|
| `deploy` | Validate, deploy, reconcile ACLs, then run the acceptance sequence |
| `freeze` | Preserve both trigger definitions, set each to `PAUSED`, and require no active source or collector run |

Both operations use the protected `prod` environment and `deploy-prod`
concurrency lock.

### Deploy operation

```text
protected prod approval
→ expose DATABRICKS_CLIENT_SECRET
→ install Databricks CLI 1.7.0
→ assert required inputs and three distinct identities
→ prove deployer can use both run_as service principals
→ bundle validate --target prod
→ bundle deploy --target prod
→ grant deployed-directory ACLs
→ resolve deployed job IDs from bundle summary
→ jobs run-now: source
→ jobs run-now: collector sweep 1
→ jobs run-now: collector sweep 2 (idempotency check)
```

The workflow has `contents: read` only. The `prod` job environment is the
credential release boundary; repository variables provide non-secret
configuration, including the optional notification JSON array. The workflow
validates that complex value and writes the ignored production target override
before bundle validation. The protected environment provides only
`DATABRICKS_CLIENT_SECRET`. On the deploy path, the workflow scopes it to
validation, deployment, directory ACL reconciliation, and acceptance runs.
Checkout, CLI installation, identity preflight, and notification preprocessing
never receive it.

After deployment, the workflow obtains `workspace.file_path` from JSON bundle
summary output, resolves its workspace object ID, and replaces the directory's
direct ACL with:

| Principal | Deployed directory permission |
|-----------|-------------------------------|
| Source runner | `CAN_READ` |
| Collector | `CAN_RUN` |

Inherited deployer and administrator access remains. Replacing direct entries
also removes obsolete runtime principals during a reviewed rotation.

The smoke check waits for the source and both collector sweeps, then explicitly
requires lifecycle `TERMINATED` and result `SUCCESS` for each. CLI lifecycle
completion alone is not treated as success. The second collector sweep proves
that a terminal AttemptKey can be rediscovered without creating duplicate
registry or invocation facts. A source failure, either collector failure, or
bundle error fails the workflow.

The workflow writes the source parent/task run IDs and both collector parent
run IDs to the GitHub job summary and emits one stable `ACCEPTANCE_RUN_IDS` log
line. Verification uses those exact IDs instead of assuming the newest
Databricks run belongs to the deployment.

### Freeze operation

```text
protected prod approval
→ expose DATABRICKS_CLIENT_SECRET only to the pause step
→ resolve exactly one source and one collector job by production name
→ preserve trigger/schedule fields and set pause_status = PAUSED
→ read both jobs back and assert PAUSED
→ assert neither job has an active run
```

The freeze job does not check out repository code, validate a bundle, deploy,
or run either workload. If an active run exists, it leaves both triggers paused
and fails; the operator waits for the active run to terminate and dispatches
`freeze` again. Runtime-identity rotation uses this gate before ownership
transfer. A later approved `deploy` restores the trigger states declared in the
bundle.

Use GitHub required reviewers and restrict the `prod` environment to `main`.
See GitHub's [deployment environments documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## Documentation workflow

```text
install requirements-docs.txt
→ zensical build --clean --strict
→ upload Pages artifact
→ deploy to GitHub Pages
```

It runs only when documentation sources, Zensical configuration, documentation
requirements, or the workflow itself change. It has `contents: read`,
`pages: write`, and `id-token: write`; that GitHub Pages OIDC permission does not
authenticate to Databricks.

## Inputs

Production input locations are defined in
[Configuration values](configuration-values.md). PR CI and the documentation
workflow must remain free of `DATABRICKS_CLIENT_SECRET`.

## Example verification

```bash
gh run list --workflow ci.yml --limit 5
gh run list --workflow deploy.yml --limit 5
gh run list --workflow docs.yml --limit 5
```
