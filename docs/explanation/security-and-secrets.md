---
icon: lucide/lock
---

# Keeping secrets out of git

A core design goal of this repo: **no Databricks workspace value and no Microsoft
Entra username appears anywhere in git** — not the host, warehouse ID, catalog,
account ID, or any token. This page explains the layers that make that true, so
you can keep it true as you extend the project.

## What counts as "sensitive" here

| Value | Why it's kept out |
|-------|-------------------|
| Workspace host (`adb-….azuredatabricks.net`) | Identifies a specific tenant/workspace |
| SQL warehouse ID | Points at specific compute |
| Unity Catalog catalog | Names a specific data namespace |
| Account ID (UUID) | Used in OIDC; identifies the account |
| Microsoft Entra username / email | Personal identity |
| PATs / client secrets / tokens | Credentials |

## The layers

### 1. Bundle variables instead of literals

`databricks.yml` declares `warehouse_id`, `catalog`, and `schema` as **bundle
variables**. The two sensitive ones — `warehouse_id` and `catalog` — default to
obvious placeholders (`REPLACE_WITH_YOUR_*`); `schema` carries the non-sensitive
default `dbt_nyc_taxi`. The job resource references `${var.warehouse_id}` etc., so
the real values are supplied at deploy time as `BUNDLE_VAR_*` — never written
down. See [Bundle configuration](../reference/bundle-config.md).

### 2. No host in the bundle

There is intentionally no `workspace.host` in `databricks.yml`. The CLI resolves
the host from `DATABRICKS_HOST` or your profile, and the `prod` target uses
`${workspace.current_user.userName}` rather than a hard-coded name.

### 3. Env-var-only dbt profile

`dbt_profiles/profiles.yml` reads every value from `env_var(...)`, so the
committed file contains no host, warehouse, catalog, or token. The deployed job
doesn't even use it — Databricks injects credentials. See
[How dbt connects to Databricks](how-dbt-connects.md).

### 4. OIDC instead of stored secrets in CI

GitHub Actions authenticates with **Workload Identity Federation** — short-lived
OIDC tokens, nothing at rest. Workspace values come from **GitHub Variables**
(`vars.*`), which are configuration, not code. Setup:
[Set up secretless CI/CD with OIDC](../how-to/set-up-oidc-cicd.md).

### 5. `.gitignore` as a backstop

Local state that *does* contain real values (because tools write it there) is
ignored so it can never be committed:

```text
.databricks/            # bundle state — includes host + your user
.databrickscfg          # CLI profiles
.venv/  target/  logs/  dbt_packages/
**/variable-overrides*.json   # local bundle variable overrides
.env.local  *.local.yml  *.local.yaml
/site/  docs/_build/    # built docs output
```

## How to verify nothing leaked

Before committing, scan the files git would actually track for the real
identifier patterns this repo forbids — host, warehouse path, tokens, Entra
email, and the account UUID:

```bash
git ls-files --cached --others --exclude-standard \
  | xargs grep -nEiI \
      -e 'adb-[0-9]+\.[0-9]+\.azuredatabricks' \
      -e '/warehouses/[0-9a-f]{8,}' \
      -e 'dapi[0-9a-f]{16,}' \
      -e '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.onmicrosoft\.com' \
      -e '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' \
  || echo "clean"
```

!!! warning "This is a quick scan, not a guarantee"
    The patterns above catch the obvious shapes, but a UUID match may be a
    legitimate `bundle.uuid` or the fixed Azure Databricks resource ID, and a
    **catalog name** is just a word — it has no distinctive pattern, so confirm
    catalog names by eye. Treat a hit as "look here", and treat *no* hit as
    "nothing obvious", not "definitely clean".

!!! tip "Placeholders are intentional"
    Strings like `adb-XXXXXXXXXXXX.NN.azuredatabricks.net`,
    `<your-warehouse-id>`, `<your-catalog>`, and `you@example.onmicrosoft.com`
    are deliberate placeholders, not real values. They show the *shape* of an
    input without revealing one.

## The one GitHub identity that stays

The repository slug `MiguelElGallo/bricks-cli` does appear — in the OIDC
federation subject (`repo:MiguelElGallo/bricks-cli:environment:prod`) and the
docs site config. That's the **public GitHub repository** itself, which is
required for the federation trust. It is not a Databricks workspace value or an
Entra username, so it's safe and necessary to keep.
