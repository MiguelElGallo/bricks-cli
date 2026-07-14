---
icon: lucide/refresh-cw
---

# Rotate the deployer secret

Replace the OAuth M2M secret used by the protected GitHub `prod` environment
without interrupting deployments.

Create the replacement before revoking the active secret. Runtime jobs do not
use this secret; they run as their own service principals.

## Prerequisites

You need:

- an OAuth U2M profile with authority to manage the deployer service principal;
- GitHub permission to update `prod` environment secrets;
- `jq` for fail-closed response validation;
- the deployer's numeric Databricks service-principal ID; and
- the approved record from the previous setup or rotation.

## 1. Bind GitHub to the sole active credential

Require exactly one active Databricks OAuth secret, record its non-secret ID,
and prove that the current GitHub value authenticates before creating anything:

```bash
set +x
set -euo pipefail
export DEPLOYER_NUMERIC_ID="<deployer-numeric-service-principal-id>"

active_before="$(
  databricks service-principal-secrets-proxy list \
    "$DEPLOYER_NUMERIC_ID" \
    --profile bricks-demo \
    --output json |
    jq -c '[.[] | select(.status == "ACTIVE")] | sort_by(.id)'
)"
[[ "$(jq -r 'length' <<< "$active_before")" == 1 ]] || {
  echo "Expected exactly one active deployer OAuth secret." >&2
  exit 1
}
OLD_SECRET_ID="$(jq -er '.[0].id' <<< "$active_before")"
export OLD_SECRET_ID

gh workflow run deploy.yml --ref main -f operation=deploy
```

Approve the protected run and require it to succeed. With exactly one active
Databricks secret, that result binds the GitHub value to `OLD_SECRET_ID` without
revealing either value. If the active set is not exactly one, stop and reconcile
the approved credential inventory; do not guess which ID to revoke.

The metadata response does not include secret values.

## 2. Create and install the replacement

Use the REST duration form live-validated during setup: a positive number of
seconds with an `s` suffix. The example uses 30 days. Recheck the sole active
old ID immediately before creation so another administrator cannot silently
change the inventory between steps.

```bash
set +x
set -euo pipefail
export OAUTH_SECRET_LIFETIME_SECONDS=2592000
[[ "$OAUTH_SECRET_LIFETIME_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
  echo "OAuth secret lifetime must be canonical positive seconds." >&2
  exit 1
}

expected_old="$(jq -cn --arg id "$OLD_SECRET_ID" '[$id] | sort')"
active_before_create="$(
  databricks service-principal-secrets-proxy list \
    "$DEPLOYER_NUMERIC_ID" \
    --profile bricks-demo \
    --output json |
    jq -c '[.[] | select(.status == "ACTIVE") | .id] | sort'
)"
[[ "$active_before_create" == "$expected_old" ]] || {
  echo "Active deployer secret set changed before rotation." >&2
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

  expected_pair="$(
    jq -cn \
      --arg old "$OLD_SECRET_ID" \
      --arg new "$created_id" \
      '[$old, $new] | unique | sort'
  )"
  [[ "$(jq -r 'length' <<< "$expected_pair")" == 2 ]]
  active_after_create="$(
    databricks service-principal-secrets-proxy list \
      "$DEPLOYER_NUMERIC_ID" \
      --profile bricks-demo \
      --output json |
      jq -c '[.[] | select(.status == "ACTIVE") | .id] | sort'
  )"
  [[ "$active_after_create" == "$expected_pair" ]] || {
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
  [[ "$active_after_install" == "$expected_pair" ]] || {
    echo "Active deployer secret set changed during installation." >&2
    exit 1
  }
  installed=true
  printf 'Record NEW_SECRET_ID=%s expires=%s\n' \
    "$created_id" "$expires_at"
)

export NEW_SECRET_ID="<recorded-new-secret-id>"
```

The GitHub command is not started until creation, JSON validation, and the
non-empty assertion succeed. Exact-set checks require `{old,new}` before and
after GitHub installation. If installation fails, the trap revokes the unused
replacement. The subshell discards the secret value on every exit and prints
only its non-secret ID and expiry. Never run this procedure under command
tracing; the sensitive subshell begins with `set +x`. Do not revoke the previous
active secret yet.

## 3. Validate the new secret

Trigger the production workflow from the reviewed `main` branch:

```bash
gh workflow run deploy.yml --ref main -f operation=deploy
```

Approve the `prod` environment and verify that:

- M2M authentication succeeds;
- `bundle validate` and `bundle deploy` succeed;
- the directory ACL reconciliation succeeds; and
- the source run and both collector sweeps complete.

The workflow never prints which secret value it used. A successful run after the
GitHub secret update is the validation.

## 4. Revoke the old secret

Only after the protected deployment succeeds, recheck that the active set is
exactly `{old,new}`, revoke the old ID, and require the result to be exactly
`{new}`:

```bash
set +x
set -euo pipefail
expected_pair="$(
  jq -cn \
    --arg old "$OLD_SECRET_ID" \
    --arg new "$NEW_SECRET_ID" \
    '[$old, $new] | unique | sort'
)"
[[ "$(jq -r 'length' <<< "$expected_pair")" == 2 ]] || {
  echo "Recorded old and new secret IDs must be distinct." >&2
  exit 1
}
active_before_revoke="$(
  databricks service-principal-secrets-proxy list \
    "$DEPLOYER_NUMERIC_ID" \
    --profile bricks-demo \
    --output json |
    jq -c '[.[] | select(.status == "ACTIVE") | .id] | sort'
)"
[[ "$active_before_revoke" == "$expected_pair" ]] || {
  echo "Active deployer secret set changed before revocation." >&2
  exit 1
}

databricks service-principal-secrets-proxy delete \
  "$DEPLOYER_NUMERIC_ID" \
  "$OLD_SECRET_ID" \
  --profile bricks-demo

expected_new="$(jq -cn --arg id "$NEW_SECRET_ID" '[$id] | sort')"
active_after_revoke="$(
  databricks service-principal-secrets-proxy list \
    "$DEPLOYER_NUMERIC_ID" \
    --profile bricks-demo \
    --output json |
    jq -c '[.[] | select(.status == "ACTIVE") | .id] | sort'
)"
[[ "$active_after_revoke" == "$expected_new" ]] || {
  echo "Old secret revocation did not leave exactly the replacement." >&2
  exit 1
}
```

Record the new expiry in the approved operational record. Do not record the
secret value.

## Success criteria

Rotation is complete when:

- the protected workflow succeeds with the replacement;
- the former secret ID is revoked;
- the active secret set is exactly the recorded replacement ID;
- the new expiry is known; and
- no secret value appears in shell history, files, Actions output, or job
  parameters.

## Recovery

If validation fails while `{old,new}` remains active, create and revoke nothing
until that exact pair is reconciled against the approved record:

- for a failure unrelated to authentication, correct the cause and retry with
  the same replacement;
- to abandon the replacement, approve revocation of the exact `new` ID, require
  the set to return to exactly `{old}`, and then repeat step 2 with a newly
  recorded candidate. This uses the already established old-ID binding and
  never creates a third active secret; and
- for any other active set, stop and reconcile every ID. Never delete an ID
  merely because it is older.

If the old ID was revoked too early, do not create ad hoc credentials. When the
sole new credential works, validate it and adopt `{new}` as the completed state.
When it cannot authenticate and its value is irrecoverable, approve revocation
of that exact sole ID, require an empty set, and return to first setup.

If a newly created value was exposed, treat its recorded ID as compromised and
follow the same state transition: `{old,new}` to `{old}` before retrying, or use
the normal one-to-two rotation path when the exposed credential is the sole
working ID. Inspect relevant logs and local history.
