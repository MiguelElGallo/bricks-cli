---
icon: lucide/key-round
---

# Authentication support

The repository uses Databricks unified authentication. The active method
depends on whether the caller is a human, credential-free CI, or the protected
production workflow.

## Support matrix

| Context | Method | Required inputs | Credential state | Repository status |
|---------|--------|-----------------|------------------|-------------------|
| Local human | OAuth U2M profile | Workspace host and browser sign-in | Sensitive cached OAuth state; no user-managed static token | Recommended |
| Pull-request CI | None | None | None | Active; offline checks only |
| Documentation workflow | None for Databricks | GitHub Pages OIDC is separate | No Databricks credential | Active |
| Production GitHub deployment | OAuth M2M | Host, service-principal client ID, client secret | Protected, rotating reusable secret | Active |
| GitHub workload identity federation | `github-oidc` | Host, client ID, account-level federation policy | No reusable secret | Unsupported by this Free Edition account |
| Personal access token | PAT | Host and token | Reusable static token | Not used |
| Azure CLI | `azure-cli` | Azure workspace and `az` session | Azure cached OAuth state | Not applicable to this AWS target |

The email address used to create or access a personal workspace does not change
the CLI authentication protocol. The limiting factor here is the Free Edition
product boundary. Its restricted interactive login-provider list is separate
from the workspace API OAuth U2M and M2M flows validated here.

## Local OAuth U2M

```text
databricks auth login --host <workspace-url> --profile <profile>
databricks auth token <profile> --output json
databricks current-user me --profile <profile>
```

The CLI opens browser sign-in and stores local OAuth state in the Databricks
configuration. `auth token` exports a short-lived token from that U2M profile;
it is not used to retrieve or display an OAuth M2M client secret. Both the
cached refresh state and the emitted one-hour bearer token are credentials.
Never log, paste into chat, or store the `auth token` JSON; extract the value
only into a short-lived environment variable as shown in the local-run guide.
See the official [OAuth U2M documentation](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-u2m).

## Production OAuth M2M

```text
DATABRICKS_AUTH_TYPE=oauth-m2m
DATABRICKS_HOST=<workspace-url>
DATABRICKS_CLIENT_ID=<deployer-application-id>
DATABRICKS_CLIENT_SECRET=<protected-environment-secret>
```

Unified authentication mints and refreshes short-lived access tokens from the
client credential. The client secret itself remains a reusable credential and
must be rotated. See the official [OAuth M2M documentation](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m).

The personal Free Edition workspace was live-tested with CLI `1.7.0` on
2026-07-14. Workspace OAuth secret creation, M2M login, and the deployer's
Service Principal User grants all worked. The REST duration form `3600s`
created a one-hour secret; M2M authenticated with it; and the temporary secret
was deleted. The bare `3600` CLI-reference example was rejected by this
workspace, while omitting the flag created the documented 730-day default.
That syntax discrepancy is not a personal-email or M2M authentication
restriction. The setup and rotation guides use the live-validated suffixed
form.

## Why GitHub OIDC is unavailable here

Databricks workload identity federation requires a federation policy. Creating
that policy is an account-level operation. Free Edition explicitly provides no
account console or account-level APIs, so this account cannot create the policy.

The general feature remains supported on eligible Databricks accounts. See
[GitHub Actions federation](https://docs.databricks.com/aws/en/dev-tools/auth/provider-github).

## Runtime job identity

The deployment service principal does not run either workload in production:

| Job | `run_as` identity |
|-----|-------------------|
| `nyc_taxi_dbt_job` | Dedicated source runner service principal |
| `dbt_observability_collector_job` | Dedicated collector service principal |

Databricks injects the runtime credential for each job. Neither job reads the
GitHub client secret.

## Free Edition boundary

!!! danger "Not a regulated production control plane"
    Free Edition is non-commercial and lacks compliance enforcement, security
    customization, private networking, support, and an SLA. The repository is a
    regulated-design reference, but the personal validation workspace is not a
    compliant production environment by itself.
