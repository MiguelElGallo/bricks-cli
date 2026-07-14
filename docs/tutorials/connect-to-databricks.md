---
icon: lucide/plug
---

# Connect to Databricks

We will sign in through the browser and save a local OAuth user-to-machine
(U2M) profile named `bricks-demo`. The profile identifies one workspace and
lets the CLI refresh short-lived OAuth access tokens for you.

## Copy the workspace URL

Open your Databricks workspace in the browser and copy its URL. An AWS Free
Edition URL has this shape:

```text
https://dbc-xxxxxxxx-xxxx.cloud.databricks.com
```

Export the complete URL, including `https://`:

```bash
export DATABRICKS_HOST="https://dbc-xxxxxxxx-xxxx.cloud.databricks.com"
```

Print it once to catch a missing character:

```bash
printf '%s\n' "$DATABRICKS_HOST"
```

The output should be the same workspace URL you copied.

## Sign in with OAuth U2M

Create the tutorial profile:

```bash
databricks auth login --host "$DATABRICKS_HOST" --profile bricks-demo
```

The CLI opens a browser. Sign in with the same identity you use for the
workspace and approve the request. The terminal should then report:

```console
Profile bricks-demo was successfully saved
```

Databricks recommends OAuth for user authorization; the CLI handles token
refresh through unified authentication. See
[OAuth U2M authorization](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-u2m).

!!! note "A personal sign-up address is not a different CLI auth type"
    Use the browser identity that already opens the workspace. The relevant
    boundary is the workspace and account tier, not whether that identity uses
    a personal email address.

## Confirm the identity

Ask the workspace who the profile represents:

```bash
databricks current-user me --profile bricks-demo --output json
```

The JSON response should contain your workspace `userName` and `active: true`.
No personal access token is needed.

## Find the tutorial inputs

List the SQL warehouses:

```bash
databricks warehouses list --profile bricks-demo
```

Free Edition normally shows its single SQL warehouse. Copy the warehouse ID;
we will export it on the deployment page.

List the catalogs next:

```bash
databricks catalogs list --profile bricks-demo
```

Choose a catalog where your user can create a schema and managed Volumes, and
copy its name. Both commands should return workspace objects without an
authentication error.

You now have three values for the next steps:

- profile: `bricks-demo`;
- SQL warehouse ID; and
- writable Unity Catalog catalog name.

[:lucide-arrow-right: Explore the dbt project](explore-the-project.md){ .md-button .md-button--primary }
