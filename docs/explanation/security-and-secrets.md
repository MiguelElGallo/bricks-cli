---
icon: lucide/lock
---

# Security and secret boundaries

This repository minimizes credential exposure and separates the workload that
produces evidence from the workload that preserves it. Those controls are
useful, but they are not a compliance certification and do not turn Free
Edition storage into regulated retention.

## Configuration is not authentication

The deployment needs several workspace-specific values:

| Value | Stored as | Reason |
|---|---|---|
| Workspace host | GitHub repository variable or local profile | Selects a workspace |
| Warehouse, catalog, schema | GitHub repository variables or local environment | Selects data and compute |
| Service-principal application IDs | GitHub repository variables | Identifies deployer and runtime identities |
| Deployer client secret | Protected GitHub `prod` environment secret | Authenticates OAuth M2M |
| Local OAuth credential | Local Databricks credential cache | Authenticates a human through U2M |

Repository variables are not treated as credentials, but keeping real workspace
identifiers out of source still reduces accidental disclosure and prevents the
example from being tied to one workspace.

The deployment client secret is different: it is confidential, must have a
bounded lifetime, and must be rotated. It never belongs in a repository
variable, bundle override file, workflow command, or job parameter.

## Four layers keep credentials out of git

### Bundle variables

`databricks.yml` references `${var.*}` rather than embedding workspace values.
Production identity variables have no defaults, so a production deployment
cannot silently inherit the human deployer's identity.

### No hard-coded workspace host

The CLI resolves the host from `DATABRICKS_HOST` or a local profile. The bundle
does not commit `workspace.host`.

### Environment-only local dbt profile

`dbt_profiles/profiles.yml` reads `DBT_HOST`, `DBT_HTTP_PATH`,
`DBT_CATALOG`, `DBT_SCHEMA`, and `DBT_ACCESS_TOKEN` from the process
environment. A short-lived U2M token should be exported only for the local
process that needs it.

### Ignored local state

Generated bundle state, local profiles, dbt targets, local override files, and
environment files remain ignored. `.gitignore` is a backstop, not permission to
place secrets in those files indefinitely.

## The production identity split

Production uses three service principals:

| Identity | Trust placed in it |
|---|---|
| Deployer | Can change the deployed definition and grants |
| Source runner | Can execute dbt, modify the dbt target, and write staging |
| Collector | Can inspect completed runs and preserve evidence |

The source runner has no access to the evidence Volume or observability base
tables. The collector can read and delete reconciled staging and write evidence,
but does not need to modify the dbt target. Runtime identities receive only
`CAN_READ` or `CAN_RUN` on deployed files, not editor or manager access.

This separation limits post-capture rewriting by the observed workload. It does
not make source-produced JSON trustworthy before capture.

## Raw evidence and sanitized views have different audiences

`manifest.json` and `run_results.json` can include relation names, compiled SQL,
arguments, messages, adapter metadata, and other operational context. Staging,
canonical archives, quarantine, and the three base Delta tables therefore
remain restricted.

Routine operators use:

- two guaranteed sanitized views: `dbt_run_health` and `dbt_node_health`; and
- three optional Lakeflow-enriched views when the collector can read
  `system.lakeflow`.

Operators should not receive `READ VOLUME` on staging or evidence, or direct
`SELECT` on the base tables merely to inspect run health.

## Hashing is integrity evidence, not provenance

The collector builds a deterministic two-file archive, addresses it by SHA-256,
writes without overwrite, and verifies the stored bytes. That makes unexpected
post-capture change detectable at the application layer.

The source runner still controls the JSON before capture and supplies the repair
and execution labels in the staging path. A compromised producer can therefore
produce false but internally consistent input. A threat model requiring
malicious-producer resistance needs an independently trusted signing or
attestation control.

The evidence Volume is also mutable by sufficiently privileged identities.
Unity Catalog governance and hashes do not make it WORM storage. A legal
write-once requirement needs a separately approved retention control.

## Native observability does not mean unrestricted observability

The repository sends no job telemetry to an external platform. dbt anonymous
usage statistics are disabled. The Jobs API performs discovery, Unity Catalog
stores the facts and evidence, and native job notifications can alert approved
internal recipients.

The notification list defaults to empty. Until recipients are explicitly
approved and configured, the jobs have notification capability but send no
failure or duration email.

Optional system-table views require broader operational read access and can lag.
Failure to refresh them does not fail artifact capture.

## Free Edition is a validation boundary

The current AWS Free Edition workspace is suitable for learning and
non-commercial functional validation. Databricks documents that Free Edition
does not provide compliance enforcement, security customization, private
networking, an SLA, or support. It may stop compute under fair-use limits and
may delete an account after prolonged inactivity. Databricks also describes
Free Edition for exploratory datasets and reserves the right to train on
uploaded data.

Use only the included public demonstration data. Never upload Personal Data,
confidential, proprietary, or regulated data to this personal workspace, and do
not treat its managed Volume as durable retention.

Therefore this repository demonstrates patterns that can be evaluated for a
regulated deployment; it is not itself evidence that a regulated production
environment exists. See
[Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations).
See also the [Free Edition comparison](https://docs.databricks.com/aws/en/getting-started/free-trial-vs-free-edition).

Operational procedures are in
[Set up M2M CI/CD](../how-to/set-up-m2m-cicd.md),
[Rotate the deployer secret](../how-to/rotate-the-deployer-secret.md), and
[Repair production runtime file access](../how-to/grant-production-runtime-access.md).
