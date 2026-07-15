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
| `.github/workflows/deploy.yml` | Push to `main` unless all changed paths are ignored; manual `deploy` or `freeze` | OAuth M2M secret | protected `prod` | `deploy-prod` |
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

Pushes to `main` select `deploy` unless every changed path matches the explicit
documentation-only `paths-ignore` list. This prevents Pages-only publication
from creating an unrelated dbt AttemptKey while other repository changes still
fail safely through production validation. A manual dispatch requires one
explicit choice:

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
→ jobs run-now: collector sweep 2 (terminal-key rediscovery exercise)
```

The workflow has `contents: read` only. The `prod` job environment is the
release boundary for both classified workspace metadata and the OAuth
credential. Checkout and CLI setup run before any step receives those values.
Each later first-party step receives only its required, automatically masked
environment Secrets; nothing exports classified metadata job-wide. The
notification step validates and normalizes its JSON, registers masks for
derived values, and writes the ignored production target override. A final
`always()` step removes local protected bundle configuration before third-party
post-job hooks run. `DATABRICKS_CLIENT_SECRET` remains narrower: on the deploy
path, only validation, deployment, directory ACL reconciliation, and acceptance
steps receive it; the freeze path exposes it only to the approved pause step.

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
completion alone is not treated as success. The second collector sweep
exercises terminal-key rediscovery; the independent production-verification
procedure proves normalized row uniqueness. A source failure, either collector
failure, or bundle error fails the workflow.

Runs produced by this workflow revision pass workspace metadata from protected
environment Secrets only to first-party steps and suppress raw workspace-aware
CLI responses. Their public log and job
summary report only that one source build and two collector sweeps succeeded;
they do not print Databricks job or run IDs. Historical Actions audit records
predating this revision may retain the older metadata summaries; changing this
workflow is not retroactive.

Independent verification resolves the exact four run IDs privately by matching
the already identity-verified source and collector jobs, one-time trigger, and
approved workflow time window. It rejects zero or multiple matches instead of
assuming the newest Databricks run belongs to the deployment.

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
