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
| `ci.yml` | pull request → `main` | `bundle validate` | `dev` |
| `deploy.yml` | push to `main` / manual | `validate` → `deploy` → `run` | `prod` |

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

1. **Create a service principal** in the Databricks **account**, and note its
   **Application (client) ID** (a UUID). That UUID is your `DATABRICKS_CLIENT_ID`.

2. **Grant it access.** Add the SP to the workspace and give it what a deploy
   needs: workspace access, permission to create the job, `CAN USE` on the SQL
   warehouse, and the ability to create and replace tables in your
   `<your-catalog>.dbt_nyc_taxi` schema — the simplest is to make the service
   principal the **owner** of that schema, so it can create, replace, and drop
   the seeds and models dbt manages.

3. **Create a federation policy** that trusts your repo. Follow
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
    | `DATABRICKS_CLIENT_ID` | the SP Application ID (UUID) from A1 | auth |
    | `DATABRICKS_WAREHOUSE_ID` | your SQL warehouse ID | `BUNDLE_VAR_warehouse_id` |
    | `DATABRICKS_CATALOG` | your Unity Catalog catalog | `BUNDLE_VAR_catalog` |
    | `DATABRICKS_SCHEMA` | e.g. `dbt_nyc_taxi` | `BUNDLE_VAR_schema` |

    !!! warning "Always set `DATABRICKS_SCHEMA`"
        Both workflows pass `BUNDLE_VAR_schema` from this Variable unconditionally.
        Leaving it unset passes an **empty** schema that overrides the committed
        `dbt_nyc_taxi` default, so set it (for example, `dbt_nyc_taxi`).

    !!! note "Repository Variables, not environment Variables"
        The workflows read `vars.*` in their top-level `env:` block, which GitHub
        evaluates before the job's `environment:` is active. Define these as
        **repository** Variables so they resolve — environment-scoped Variables
        would be empty there.

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
    Open a pull request to run `ci.yml` (it validates against `dev`); merge to
    `main` to run `deploy.yml` (it deploys and runs on `prod`).

## Related

- [Deploy to production](deploy-to-production.md)
- Reference: [Configuration values](../reference/configuration-values.md)
- Explanation: [Keeping secrets out of git](../explanation/security-and-secrets.md)
