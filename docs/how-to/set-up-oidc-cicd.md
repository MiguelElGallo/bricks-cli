---
icon: lucide/shield-check
---

# Set up secretless CI/CD with OIDC

The workflows in `.github/workflows/` deploy the bundle from GitHub Actions using
**Workload Identity Federation** (OIDC): GitHub mints a short-lived OIDC token for
the job, and Databricks exchanges it for a short-lived access token because a
*federation policy* trusts that exact GitHub identity.

!!! info "Why this is the modern default"
    A PAT or OAuth client secret would have to be stored as a GitHub secret,
    rotated, and could leak. OIDC tokens are **minted per-run and expire in
    minutes**, and trust is scoped to one repo + environment. Databricks
    recommends this over secrets. Background:
    [The authentication model](../explanation/authentication.md).

## What you'll wire up

| File | Trigger | Action | Environment |
|------|---------|--------|-------------|
| `ci.yml` | pull request → `main` | Ruff, ty, pytest, offline dbt parse/list, bundle validate + plan | `dev` |
| `deploy.yml` | push to `main` / manual | `validate` → `deploy` → source dbt build | `prod` |

Both authenticate with just these inputs:

```yaml
permissions:
  id-token: write          # lets the job mint a GitHub OIDC token
  contents: read
env:
  DATABRICKS_AUTH_TYPE: github-oidc
  DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
  DATABRICKS_CLIENT_ID: ${{ vars.DATABRICKS_CLIENT_ID }}   # SP UUID — not a secret
```

## Part A — Databricks side

1. **Create a deployment service principal** in the Databricks **account**, and
   note its **Application (client) ID** (a UUID). That UUID is your
   `DATABRICKS_CLIENT_ID`.

2. **Create two dedicated production runtime service principals.** Add both to
   the workspace. Record the dbt runner's Application ID as
   `DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME`, and record the collector's as
   `DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME`. Keep both distinct from the
   deployer and from each other. The deployment principal must have `CAN USE`
   on both runtime identities.

3. **Grant each identity only its role.** The deployment principal needs
   workspace access, permission to create/manage the jobs, and `USE CATALOG` plus
   `CREATE SCHEMA` on the selected catalog. It creates the target-scoped
   observability schema and both managed Volumes and must be allowed to manage
   their grants.

   The dbt runner needs `CAN USE` on the SQL warehouse, access to the target dbt
   catalog/schema, `USE SCHEMA` on the observability schema, and `READ VOLUME`
   plus `WRITE VOLUME` only on the staging Volume. dbt may read its own target
   directory during the invocation. The runner must not receive evidence-Volume
   or observability base-table access.

   The collector needs read access to the source job and `USE CATALOG` on the
   observability catalog. The bundle grants it `CAN_VIEW` on the source job;
   `USE SCHEMA`, `CREATE TABLE`, `SELECT`, and `MODIFY` on the dedicated
   observability schema; and `READ VOLUME` plus `WRITE VOLUME` on both staging
   and evidence. Finally, grant the collector `USE CATALOG`, `USE SCHEMA`, and
   `SELECT` on `system.lakeflow.job_run_timeline` and
   `system.lakeflow.job_task_run_timeline` so it can create the scoped Lakeflow
   health views. Follow least privilege rather than granting catalog-wide
   ownership.

4. **Create a federation policy** that trusts your repo. Follow
   [Enable workload identity federation for GitHub Actions](https://learn.microsoft.com/azure/databricks/dev-tools/auth/provider-github).
   Run this with an **account-level** Databricks CLI context (an account-console
   host `https://accounts.azuredatabricks.net` plus your `account_id`, signed in as
   an account admin), not the workspace profile from the tutorial. The CLI form is:

    ```bash
    databricks account service-principal-federation-policy create <SP_NUMERIC_ID> \
      --json '{
        "oidc_policy": {
          "issuer":    "https://token.actions.githubusercontent.com",
          "audiences": ["<DATABRICKS_HOST>/oidc/v1/token", "<DATABRICKS_ACCOUNT_ID>"],
          "subject":   "repo:MiguelElGallo/bricks-cli:environment:prod"
        }
      }'
    ```

!!! danger "Two details cause almost every `unauthorized` failure"
    - **`<SP_NUMERIC_ID>` is a positional argument** — the service principal's
      *numeric* ID, **not** the `--service-principal-id` flag (there is no such
      flag) and not the client-ID UUID.
    - **`audiences` must match the `aud` the CLI actually sends.** When you
      authenticate to a *workspace* host with `DATABRICKS_AUTH_TYPE=github-oidc`,
      the CLI mints a GitHub token whose `aud` is your workspace **OIDC token
      endpoint** — `<DATABRICKS_HOST>/oidc/v1/token` (your `DATABRICKS_HOST`
      already includes the `https://` scheme) — not the bare account ID. Listing
      both that URL and your account ID (as shown above) matches whichever the
      runtime sends. A GitHub org URL here will **not** match the minted token,
      and every run fails with `unauthorized`.

!!! warning "You need one policy per environment"
    The `subject` must match the token's `sub` claim **exactly**, and `sub` is
    driven by the workflow's `environment:`. This repo deploys from `prod`
    (`deploy.yml`) but validates from `dev` (`ci.yml`), so create a **second**
    policy identical except for:

    ```
    repo:MiguelElGallo/bricks-cli:environment:dev
    ```

## Part B — GitHub side

1. Add these configuration values as **repository Variables** under
   **Settings → Secrets and variables → Actions → Variables**:

    | Variable | Value | Fills |
    |----------|-------|-------|
    | `DATABRICKS_HOST` | `https://adb-XXXXXXXXXXXX.NN.azuredatabricks.net` | host |
    | `DATABRICKS_CLIENT_ID` | deployment SP Application ID (UUID) from A1 | auth and `BUNDLE_VAR_prod_deployer_service_principal_name` |
    | `DATABRICKS_WAREHOUSE_ID` | your SQL warehouse ID | `BUNDLE_VAR_warehouse_id` |
    | `DATABRICKS_CATALOG` | your Unity Catalog catalog | `BUNDLE_VAR_catalog` |
    | `DATABRICKS_SCHEMA` | e.g. `dbt_nyc_taxi` | `BUNDLE_VAR_schema` |
    | `DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME` | dedicated production dbt-runner Application ID | `BUNDLE_VAR_prod_run_as_service_principal_name` |
    | `DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME` | dedicated production collector Application ID | `BUNDLE_VAR_prod_collector_service_principal_name` |

    !!! warning "Always set `DATABRICKS_SCHEMA`"
        Both workflows pass `BUNDLE_VAR_schema` from this Variable unconditionally.
        Leaving it unset passes an **empty** schema that overrides the committed
        `dbt_nyc_taxi` default, so set it (for example, `dbt_nyc_taxi`).

    !!! note "Repository Variables, not environment Variables"
        The workflows read `vars.*` in their top-level `env:` block, which GitHub
        evaluates before the job's `environment:` is active. Define these as
        **repository** Variables so they resolve — environment-scoped Variables
        would be empty there.

    !!! info "Observability defaults"
        `dbt_observability_<target>`, `dbt_artifacts_staging`, `dbt_artifacts`,
        and the 900-second health threshold have committed base defaults.
        Development mode also prefixes the schema resource for the CI
        principal. The current workflows leave
        `notification_emails` at its empty default. Adding recipients to CI is
        a separate reviewed change because it is a complex variable and may
        create an outbound communication channel.

    !!! note "Variable vs. secret for the client ID"
        A client ID isn't a credential, so a repo **Variable** is fine. The
        official MS Learn example stores it as a **Secret** instead — either
        works; if you prefer a secret, read it with `${{ secrets.* }}` in the
        workflow.

2. Create **Environments** named `dev` and `prod`
   (**Settings → Environments**). The `environment:` in each workflow both gates
   the run and shapes the OIDC `subject`. Add **required reviewers** on `prod`
   for a manual approval gate.

!!! check "Run the workflows"
    Open a pull request to run `ci.yml` (local quality gates, offline dbt graph
    validation, then bundle validation and a read-only plan against `dev`);
    merge to `main` to run `deploy.yml` (it deploys both jobs and runs the source
    dbt build on `prod`; the independent collector captures completed attempts
    on its 15-minute production schedule).

## Related

- [Deploy to production](deploy-to-production.md)
- Reference: [Configuration values](../reference/configuration-values.md)
- Explanation: [Keeping secrets out of git](../explanation/security-and-secrets.md)
