---
icon: lucide/download
---

# Install the Databricks CLI

We will install the current Databricks CLI, verify it, and clone this
repository. This tutorial uses the modern Go-based CLI, not the legacy Python
package named `databricks-cli`.

## Install the CLI

In a macOS terminal, install the official Homebrew formula directly from the
Databricks tap:

```bash
brew install databricks/tap/databricks
```

Homebrew should finish with a successful installation summary and no error.
This is one of the installation methods in the official
[Databricks CLI installation guide](https://docs.databricks.com/aws/en/dev-tools/cli/install).

## Check the version

Run:

```bash
databricks version
```

You should see a modern CLI version, for example:

```console
Databricks CLI v1.7.0
```

The exact current version can be newer. A version beginning with `v1.` confirms
that this tutorial's CLI is installed.

## Clone the repository

Move to a directory where you keep source code, then clone and enter the
project:

```bash
git clone https://github.com/MiguelElGallo/bricks-cli.git
cd bricks-cli
```

Confirm that you are at the bundle root:

```bash
test -f databricks.yml && test -f dbt_project.yml && pwd
```

The command should print a path ending in `/bricks-cli`. You now have both the
bundle definition and the dbt project in your working directory.

[:lucide-arrow-right: Connect to Databricks](connect-to-databricks.md){ .md-button .md-button--primary }
