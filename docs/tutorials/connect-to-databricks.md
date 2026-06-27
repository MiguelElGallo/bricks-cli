---
icon: lucide/plug
---

# Connect to Databricks

The CLI can do nothing until it knows **which workspace** to talk to and **who
you are**. In this step you'll set both up using your existing Azure login.

!!! info "Unified authentication"
    Every Databricks command — including `bundle deploy` — looks for credentials
    in the same well-defined order, so the same setup works locally and in CI.
    The full model is explained in
    [The authentication model](../explanation/authentication.md). For now, we'll
    use the simplest option for Azure.

## Sign in to Azure

Because the workspace is Azure Databricks and you own (or can access) the
subscription, you can let the CLI reuse your `az` session:

```bash
az login          # opens a browser if you're not already signed in
az account show   # confirm you're in the right subscription
```

!!! tip
    If `az account show` lists the wrong subscription, switch with
    `az account set --subscription "<name-or-id>"` before continuing.

## Create a profile

Profiles live in `~/.databrickscfg`. Each one names a workspace host and how to
authenticate. Add a profile that points at your workspace and uses Azure CLI
auth:

```ini title="~/.databrickscfg"
[bricks-demo]
host      = https://adb-XXXXXXXXXXXX.NN.azuredatabricks.net
auth_type = azure-cli
```

Replace the `host` with your own workspace URL. (1)
{ .annotate }

1.  You'll find it in the address bar when you open your workspace, or under
    **Settings**. It looks like `https://adb-<digits>.<n>.azuredatabricks.net`.

!!! note "Why `auth_type = azure-cli`?"
    It tells the CLI to mint short-lived Microsoft Entra ID tokens from your `az`
    session on demand. The profile itself stores only a host and an auth
    *method*.

## Prove it works

Ask the workspace who you are:

```bash
databricks current-user me -p bricks-demo
```

```console
you@example.onmicrosoft.com
```

!!! check "Connected!"
    If you see your own username, the CLI is authenticated against your
    workspace. That same identity is what will deploy the bundle in step 4.

??? question "Got an error instead?"
    - **`default auth: cannot configure default credentials`** — the profile
      name or `host` is off, or `az` isn't logged in. Re-run `az login` and
      double-check the `-p bricks-demo` flag.
    - **`401 Unauthorized`** — your Azure identity may not be a member of the
      workspace yet. Ask a workspace admin to add you.

## Recap

You now have:

- [x] an **Azure session** (`az login`),
- [x] a **profile** in `~/.databrickscfg` that names your workspace and uses
      `azure-cli` auth, and
- [x] a **confirmed identity** from `databricks current-user me`.

That's the whole local setup — your Azure login is doing the work. Next, let's
look at the dbt project you're about to deploy.

[:lucide-arrow-right: Explore the dbt project](explore-the-project.md){ .md-button .md-button--primary }
