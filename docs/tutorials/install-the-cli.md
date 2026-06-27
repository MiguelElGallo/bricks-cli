---
icon: lucide/download
---

# Install the Databricks CLI

The first step is to get the **Databricks CLI** — a single, dependency-free
binary that talks to the Databricks REST APIs and drives Declarative Automation
Bundles. The same binary works on Azure, AWS, and GCP; this tutorial targets
**Azure Databricks**.

!!! warning "Use the new CLI, not the legacy one"
    The old "legacy" Databricks CLI was a Python package
    (`pip install databricks-cli`). The current CLI is a **Go binary** from
    [github.com/databricks/cli](https://github.com/databricks/cli). Bundles
    require the new binary — that's the one you want.

## Install it

Pick whichever line fits your machine. They all give you the same binary.

=== "Homebrew (macOS / Linux)"

    ```bash
    brew tap databricks/tap
    brew install databricks
    ```

=== "Install script"

    ```bash
    curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
    ```

=== "Direct download"

    Grab a specific release binary from the
    [releases page](https://github.com/databricks/cli/releases) and put it on
    your `PATH`.

!!! tip "Pinning a version"
    For reproducible deployments, pin an exact version — that's what the CI in
    this repo does (`databricks/setup-cli` with a fixed `version:`). You'll see
    it again when we [set up CI/CD](../how-to/set-up-oidc-cicd.md).

## Check it

Now confirm the binary is on your `PATH`:

```bash
databricks version
```

You should see something like:

```console
Databricks CLI v1.5.0
```

!!! check "That's it"
    If you got a version number back, the CLI is installed and ready. If your
    shell says `command not found`, open a new terminal (so it picks up the
    updated `PATH`) and try again.

## A quick look around

The CLI groups commands by area — run `databricks --help` to see them. The group
you'll use throughout this guide is `bundle`, which deploys the project:

```bash
databricks bundle --help
```

!!! info "Want the full list?"
    The [CLI commands reference](../reference/cli-commands.md) lists the command
    groups you'll use here and the handy global flags (`-o json`, `--debug`).

## Recap

In this step you:

- [x] learned the difference between the **legacy** and the **new** CLI,
- [x] **installed** the new binary, and
- [x] **confirmed** it with `databricks version`.

Next, you'll point the CLI at a workspace and prove who you are using your Azure
login.

[:lucide-arrow-right: Connect to Databricks](connect-to-databricks.md){ .md-button .md-button--primary }
