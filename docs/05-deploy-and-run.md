# 05 – Deploy & run (and secretless CI/CD with OIDC)

## Prerequisites

- Databricks CLI v1.5.0 ([docs/01](01-databricks-cli.md)) and an authenticated
  session ([docs/02](02-authentication.md)).
- Access to a **SQL warehouse** and a **Unity Catalog** catalog you can write to.
- The bundle keeps no workspace values in git, so provide them at deploy time as
  `BUNDLE_VAR_*` environment variables (in CI these come from GitHub Variables —
  see below):

  ```bash
  export DATABRICKS_HOST="https://adb-XXXXXXXXXXXX.NN.azuredatabricks.net"
  export BUNDLE_VAR_warehouse_id="<your-warehouse-id>"
  export BUNDLE_VAR_catalog="<your-catalog>"
  export BUNDLE_VAR_schema="dbt_nyc_taxi"   # optional; this is the default
  ```

## Deploy and run from your machine

From the repo root (with the variables above exported):

```bash
# 1. Resolve and type-check the bundle for a target
databricks bundle validate --target dev

# 2. (optional) preview what will change
databricks bundle plan --target dev

# 3. Upload files + create/update resources — direct deployment, no Terraform
databricks bundle deploy --target dev

# 4. Run the dbt job now (seed → table → test) on serverless compute
databricks bundle run nyc_taxi_dbt_job --target dev

# inspect / clean up
databricks bundle summary --target dev
databricks bundle destroy --target dev
```

In `dev` (development mode) the job is created as `[dev <you>] nyc_taxi_dbt_job`
with its schedule paused, so nothing runs until you ask it to. Deploy to `prod`
by swapping `--target prod`.

## Secretless CI/CD with GitHub OIDC

The workflows in `.github/workflows/` deploy the bundle **without any stored
token or client secret**. They use **Workload Identity Federation**: GitHub mints
a short‑lived OIDC token for the job, and Databricks exchanges it for a
short‑lived access token because a *federation policy* trusts that exact GitHub
identity. Databricks strongly recommends this over OAuth secrets or PATs.

### What the workflows do

| File | Trigger | Action |
|------|---------|--------|
| `ci.yml` | pull request → `main` | `databricks bundle validate --target dev` |
| `deploy.yml` | push to `main` / manual | `validate` → `deploy` → `run` on `prod` |

Both rely only on:

```yaml
permissions:
  id-token: write          # lets the job mint a GitHub OIDC token
  contents: read
env:
  DATABRICKS_AUTH_TYPE: github-oidc
  DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
  DATABRICKS_CLIENT_ID: ${{ vars.DATABRICKS_CLIENT_ID }}  # SP UUID — not a secret
steps:
  - uses: actions/checkout@v4
  - uses: databricks/setup-cli@v1.5.0
    with: { version: 1.5.0 }
  - run: databricks bundle deploy --target prod
```

### One‑time setup

**A. Databricks side** — create a service principal and trust your repo:

1. Add a **service principal** in the Databricks account; note its
   **Application (client) ID** — that's `DATABRICKS_CLIENT_ID`.
2. Add the SP to the workspace and grant it what the deploy needs: workspace
   access, permission to create the job, use of the SQL warehouse, and
   write access to your `<your-catalog>.dbt_nyc_taxi` schema.
3. Create a **GitHub Actions federation policy** for the SP. Follow
   [Enable workload identity federation for GitHub Actions](https://learn.microsoft.com/azure/databricks/dev-tools/auth/provider-github).
   The policy pins the GitHub OIDC **issuer** and the **subject** (the federated
   identity). For an environment‑gated deploy the subject is:

   ```
   repo:MiguelElGallo/bricks-cli:environment:prod
   ```

   Equivalent CLI (account admin), shown with placeholders. Two details matter:
   the service principal's **numeric ID is a positional argument**, and
   **`audiences` is your Azure Databricks account ID** — that is the value the CLI
   sends as the token's `aud` claim when `DATABRICKS_AUTH_TYPE=github-oidc` (it
   defaults to the account ID if omitted). Putting a GitHub org URL here would not
   match the minted token and CI would fail with `unauthorized`.

   ```bash
   databricks account service-principal-federation-policy create <SP_NUMERIC_ID> \
     --json '{
       "oidc_policy": {
         "issuer":    "https://token.actions.githubusercontent.com",
         "audiences": ["<DATABRICKS_ACCOUNT_ID>"],
         "subject":   "repo:MiguelElGallo/bricks-cli:environment:prod"
       }
     }'
   ```

   Create **one policy per environment**: the subject must equal the token's `sub`
   exactly, and this repo deploys from `prod` (`deploy.yml`) but validates from
   `dev` (`ci.yml`). Add a second policy that is identical except for the subject
   `repo:MiguelElGallo/bricks-cli:environment:dev`. Find the account ID at
   **accounts.azuredatabricks.net → Settings**.

   > The **subject must match exactly** what GitHub puts in the token's `sub`
   > claim, which is driven by the workflow's `environment:` (and ref). Mismatch
   > is the #1 cause of `unauthorized` in CI.

**B. GitHub side** — give the workflows their non‑secret inputs:

1. Repo (or environment) **Variables** (Settings → Secrets and variables →
   Actions → Variables). None of these are secrets:
   - `DATABRICKS_HOST` = `https://adb-XXXXXXXXXXXX.NN.azuredatabricks.net`
   - `DATABRICKS_CLIENT_ID` = the SP Application ID from step A1. A client ID is
     not a credential, so a repo **Variable** is fine here; the official MS Learn
     example stores it as a **Secret** instead — either works.
   - `DATABRICKS_WAREHOUSE_ID` = your SQL warehouse ID (fills `BUNDLE_VAR_warehouse_id`).
   - `DATABRICKS_CATALOG` = the Unity Catalog catalog (fills `BUNDLE_VAR_catalog`).
   - `DATABRICKS_SCHEMA` = the target schema, e.g. `dbt_nyc_taxi` (fills `BUNDLE_VAR_schema`).
2. Create **Environments** named `dev` and `prod` (Settings → Environments). Add
   required reviewers on `prod` if you want a manual approval gate; the
   `environment:` in the workflow both gates the deploy and shapes the OIDC
   subject.

That's it — no `DATABRICKS_TOKEN`, no client secret, nothing to rotate.

### Why not a PAT or client secret?

A PAT or OAuth client secret would have to be stored as a GitHub secret, rotated,
and could leak. OIDC tokens are **minted per‑run and expire in minutes**, and the
trust is scoped to one repo + environment. It is the modern, recommended path.

---
Back to the [README](../README.md) · or revisit [03 – Asset Bundles](03-asset-bundles.md).
