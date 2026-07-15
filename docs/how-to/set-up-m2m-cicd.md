---
icon: lucide/bot
---

# Set up OAuth M2M CI/CD

Configure the protected GitHub `prod` environment so
`.github/workflows/deploy.yml` can deploy as the dedicated Databricks deployer
service principal.

This repository uses OAuth M2M because its AWS Free Edition workspace cannot
create the account-level federation policy required for GitHub OIDC.

## Prerequisites

You need:

- workspace-admin access through a working OAuth U2M profile;
- GitHub administrator access to the repository;
- GitHub CLI authenticated to the repository, or equivalent UI access;
- `jq` available locally for strict JSON parsing;
- three existing workspace service principals: deployer, runner, and collector;
- a SQL warehouse, parent catalog, and separate production dbt schema; and
- the numeric Databricks service-principal ID for the deployer, not only its
  application/client ID.

Verify the local profile:

```bash
databricks auth describe --profile bricks-demo
databricks current-user me --profile bricks-demo
```

## 1. Record the three application IDs

List workspace service principals:

```bash
databricks service-principals list \
  --profile bricks-demo \
  --output json |
  jq -r '.[] | [.id, .applicationId, .displayName] | @tsv'
```

Record:

- the deployer's numeric `id` and `applicationId`;
- the runner's `applicationId`; and
- the collector's `applicationId`.

The deployer application ID becomes `DATABRICKS_CLIENT_ID`. The numeric ID is
used only to create and manage the deployer's OAuth secrets.

## 2. Create the protected production environment

Create a GitHub environment named `prod`. Configure:

- at least one required reviewer;
- deployment branches restricted to `main`; and
- no bypass path that releases the Databricks secret to unreviewed code.

GitHub environment secrets become available only after the protection rules
pass. See
[Deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## 3. Store protected production metadata

Load the approved values into the current shell through your internal
secret-management process. Do not enable command tracing. Then store every
workspace-specific value as a protected `prod` environment Secret so GitHub
masks it before any workflow command runs:

```bash
set +x
set -euo pipefail
: "${DATABRICKS_HOST:?load the approved workspace host}"
: "${DATABRICKS_CLIENT_ID:?load the deployer application ID}"
: "${DATABRICKS_WAREHOUSE_ID:?load the approved warehouse ID}"
: "${DATABRICKS_CATALOG:?load the production catalog}"
: "${DATABRICKS_SCHEMA:?load the production dbt schema}"
: "${DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME:?load the runner application ID}"
: "${DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME:?load the collector application ID}"
DATABRICKS_NOTIFICATION_EMAILS="${DATABRICKS_NOTIFICATION_EMAILS:-[]}"

for name in \
  DATABRICKS_HOST \
  DATABRICKS_CLIENT_ID \
  DATABRICKS_WAREHOUSE_ID \
  DATABRICKS_CATALOG \
  DATABRICKS_SCHEMA \
  DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME \
  DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME \
  DATABRICKS_NOTIFICATION_EMAILS
do
  printf '%s' "${!name}" | gh secret set "$name" --env prod
done
```

Set `DATABRICKS_NOTIFICATION_EMAILS` to an approved JSON array before the loop
when native job email is allowed. Otherwise the stored value is `[]` and the
workflow sends no outbound job email.

Although most values are identifiers rather than credentials, storing them as
environment Secrets enables GitHub's automatic redaction before a step runs.
The workflow also suppresses raw workspace responses and explicitly masks
derived values. Keep the approved values in the internal change record because
GitHub cannot reveal them after storage.

## 4. Create and store the deployer secret

Choose the shorter lifetime required by policy. The REST duration syntax is a
positive number of seconds followed by `s`; for example, `2592000s` is 30 days.
On 2026-07-14 this workspace and CLI `1.7.0` live-validated `3600s` end to end.
The bare `3600` form shown in the CLI command reference was rejected here, so
the example deliberately includes the suffix. Omitting the flag also worked,
but created the documented 730-day default.

Before first setup, require the dedicated deployer to have no active OAuth
secret. If an approved GitHub credential already exists, stop and use
[Rotate the deployer secret](rotate-the-deployer-secret.md) instead; secret
metadata cannot otherwise prove which value GitHub holds.

Capture the one-time response only in a short-lived subshell variable, validate
its secret and expiry, and then send only the secret to GitHub through standard
input:

```bash
set +x
set -euo pipefail
export DEPLOYER_NUMERIC_ID="<deployer-numeric-service-principal-id>"
export OAUTH_SECRET_LIFETIME_SECONDS=2592000

[[ "$OAUTH_SECRET_LIFETIME_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
  echo "OAuth secret lifetime must be canonical positive seconds." >&2
  exit 1
}
active_before="$(
  databricks service-principal-secrets-proxy list \
    "$DEPLOYER_NUMERIC_ID" \
    --profile bricks-demo \
    --output json |
    jq -c '[.[] | select(.status == "ACTIVE") | .id] | sort'
)"
[[ "$active_before" == '[]' ]] || {
  echo "Expected no active deployer OAuth secrets; refusing first setup." >&2
  exit 1
}

(
  # Disable inherited command tracing before any response or secret exists.
  set +x
  set -euo pipefail
  response=""
  replacement=""
  created_id=""
  expires_at=""
  installed=false

  cleanup() {
    if [[ "$installed" != true && -n "$created_id" ]]; then
      databricks service-principal-secrets-proxy delete \
        "$DEPLOYER_NUMERIC_ID" \
        "$created_id" \
        --profile bricks-demo >/dev/null
    fi
    unset response replacement created_id expires_at installed
  }
  trap cleanup EXIT

  response="$(
    databricks service-principal-secrets-proxy create \
      "$DEPLOYER_NUMERIC_ID" \
      --lifetime "${OAUTH_SECRET_LIFETIME_SECONDS}s" \
      --profile bricks-demo \
      --output json
  )"
  replacement="$(
    jq -er '.secret | select(type == "string" and length > 0)' \
      <<< "$response"
  )"
  created_id="$(jq -er '.id | select(type == "string" and length > 0)' <<< "$response")"
  expires_at="$(jq -er '.expire_time | select(type == "string" and length > 0)' <<< "$response")"
  [[ -n "$replacement" ]]

  expected_active="$(jq -cn --arg id "$created_id" '[$id] | sort')"
  active_after_create="$(
    databricks service-principal-secrets-proxy list \
      "$DEPLOYER_NUMERIC_ID" \
      --profile bricks-demo \
      --output json |
      jq -c '[.[] | select(.status == "ACTIVE") | .id] | sort'
  )"
  [[ "$active_after_create" == "$expected_active" ]] || {
    echo "Active deployer secret set changed unexpectedly." >&2
    exit 1
  }

  printf '%s' "$replacement" |
    gh secret set DATABRICKS_CLIENT_SECRET --env prod

  active_after_install="$(
    databricks service-principal-secrets-proxy list \
      "$DEPLOYER_NUMERIC_ID" \
      --profile bricks-demo \
      --output json |
      jq -c '[.[] | select(.status == "ACTIVE") | .id] | sort'
  )"
  [[ "$active_after_install" == "$expected_active" ]] || {
    echo "Active deployer secret set changed during installation." >&2
    exit 1
  }
  installed=true
  printf 'Installed OAuth secret metadata: id=%s expires=%s\n' \
    "$created_id" "$expires_at"
)
```

The secret value is returned only when created. The GitHub command is not
started until creation, JSON validation, and the non-empty assertion all
succeed. Exact active-set checks reject pre-existing or concurrently added
credentials. If installation fails, the trap revokes the unused credential.
The subshell discards the response and secret variables on every exit; only the
non-secret ID and expiry are printed. Do not print the value, save it to a file,
or pass it as a command-line argument. Never run this procedure under command
tracing; the sensitive subshell begins with `set +x` as a second guard.

Confirm that metadata exists without retrieving the value:

```bash
databricks service-principal-secrets-proxy list \
  <deployer-numeric-service-principal-id> \
  --profile bricks-demo \
  --output json

gh secret list --env prod
```

See the official
[service-principal secret commands](https://docs.databricks.com/aws/en/dev-tools/cli/reference/service-principal-secrets-proxy-commands).
The official
[OAuth M2M guide](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m)
documents the five-secret, 730-day maximum. The REST
[service-principal secret API](https://docs.databricks.com/api/account/serviceprincipalsecrets/create)
defines the suffixed duration form.

## 5. Grant production prerequisites

Complete [Grant production prerequisites](grant-production-prerequisites.md).
It gives the deployer authority to assign the two `run_as` identities and
documents the minimum external warehouse, workspace, and Unity Catalog access
for the runner and collector.

Do not make the deployer an account administrator merely to deploy this
bundle.

## 6. Check configuration metadata

Confirm that GitHub contains the intended names without retrieving any value:

```bash
gh secret list --env prod
gh api "repos/<owner>/<repo>/environments/prod"
```

This setup guide standardizes on nine Secret names, including an explicit
`DATABRICKS_NOTIFICATION_EMAILS=[]` baseline. The workflow also accepts that
optional Secret being absent and applies the same empty-list default. Compare
the three approved application IDs in the internal change record and require
them to be pairwise distinct. `DATABRICKS_CLIENT_SECRET` must exist only in the
protected `prod` environment.

Do not trigger the workflow as part of identity setup. Deployment is a separate
reviewed operation.

## Success criteria

The setup is complete when:

- the `prod` environment requires approval and accepts deployments only from
  `main`;
- the protected environment contains this guide's explicit nine-Secret
  baseline;
- the deployer has exactly one active OAuth secret, with its non-secret ID and
  expiry recorded;
- protected environment Secrets contain all production inputs, with three
  distinct application IDs recorded internally; and
- the deployer, runner, and collector prerequisites have been verified.

Continue with [Deploy to production](deploy-to-production.md). That guide owns
the first workflow run and acceptance check.

## Recovery

If M2M authentication fails, preserve the exact-set invariant:

1. confirm the host, deployer application ID, and
   `DATABRICKS_AUTH_TYPE=oauth-m2m` configuration;
2. list the ACTIVE deployer secret IDs without creating or revoking anything;
3. with zero ACTIVE IDs, retry first setup after correcting the cause;
4. with exactly one approved ID, correct configuration and retry the protected
   workflow; once it succeeds, use the rotation guide if replacement is still
   required; and
5. with an unknown ID or any other set, stop and reconcile every ID against the
   approved record. If the one-time value is irrecoverable, revoke only the
   explicitly approved sole ID, confirm the set is empty, and then retry first
   setup.

Never create a second credential as an ad hoc recovery from first setup.

If secret creation succeeded but installation failed, the trap attempts to
revoke the unused credential. Re-list the exact active set and stop if it is not
empty; do not retry until the orphan is revoked. Never recover by printing the
secret into workflow logs.

If `run_as` assignment fails later, verify the deployer's Service Principal
User role on both runtime principals. If job execution fails after deployment,
follow [Repair production runtime file access](grant-production-runtime-access.md).
