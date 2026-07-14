---
icon: lucide/badge-check
---

# Runtime versions

These are the exact versions validated by source, CI, and deployment. Direct
dependency pins are reproducible top-level inputs, not a complete transitive
lockfile.

## Version matrix

| Component | Version/range | Used by |
|-----------|---------------|---------|
| Databricks CLI | `1.7.0` | Production GitHub deployment |
| Python project | `>=3.10,<3.14` | Local tests and type model |
| CI Python | `3.13` | Pull-request workflow |
| Ruff target Python | `3.10` | Linting and formatting |
| ty environment Python | `3.10` | Static type checking |
| dbt Core | `1.11.11` | Local development and source serverless job |
| dbt-databricks | `1.12.2` | Local development and source serverless job |
| Databricks SDK for Python | `0.117.0` | Local tests and collector serverless job |
| pytest | `9.1.1` | Unit tests |
| Ruff | `0.15.21` | Lint and format checks |
| ty | `0.0.58` | Type checking |
| Zensical | `0.0.46` | Documentation build |
| Collector parser | `1.0.0` | Registry and invocation facts |
| dbt manifest schema | `v12` | Artifact parser |
| dbt run-results schema | `v6` | Artifact parser |

## Serverless environments

Both job environments use Databricks serverless `environment_version: "4"`.

| Environment key | Job | Dependencies |
|-----------------|-----|--------------|
| `default` | Source | `dbt-core==1.11.11`, `dbt-databricks==1.12.2` |
| `collector` | Collector | `databricks-sdk==0.117.0` |

`databricks-sdk==0.117.0` is the newest SDK version accepted by the pinned
`dbt-databricks` constraint (`<0.118.0`).

## Compatibility boundary

!!! warning "Artifact schema is strict"
    The collector accepts exactly manifest `v12` and run-results `v6`. A dbt
    upgrade that changes either schema is quarantined with
    `UNSUPPORTED_ARTIFACT_SCHEMA` until the parser and tests are updated.

The validated target is Databricks Free Edition on AWS. Free Edition provides
serverless-only compute, one limited SQL warehouse, and at most five concurrent
job tasks. It does not provide an SLA, compliance enforcement, security
customization, private networking, an account console, or account-level APIs.
See the official [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations).

CLI `1.7.0` workspace OAuth secret creation was also tested live. The REST
duration form `--lifetime 3600s` created a one-hour secret; OAuth M2M and both
runtime principals through `permission eq 'servicePrincipal/use'` were then
verified; and the temporary credential was deleted. The bare `3600` example in
the CLI reference was rejected by this workspace, while omitting the flag
created the documented 730-day default. The setup guide therefore uses the
live-validated suffixed duration form.

## Verification

```bash
databricks version
python --version
dbt --version
python -m pip show databricks-sdk ruff ty pytest zensical
```
