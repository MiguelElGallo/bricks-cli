---
icon: lucide/archive-x
---

# Decommission the production deployment and evidence

Permanently remove the production jobs and observability evidence through one
reviewed, short-lived GitHub workflow. The workflow uses the protected `prod`
environment and the existing deployer OAuth M2M identity; a human U2M profile
must not destroy production.

The bundle intentionally protects the production schema and both managed
Volumes. Removing those guards is authorization for one decommission operation,
not permission to run the ordinary deploy-and-run workflow again.

!!! danger "This procedure permanently deletes operational evidence"

    Complete retention, legal, security, data-owner, recovery, and change-control
    decisions before opening the destructive change. A content hash is not a
    WORM or legal-hold control, and `bundle destroy` cannot be undone.

## 1. Record the decision and freeze the workload

Record all of the following in the approved change:

- workspace host and workload owner;
- bundle name `bricks_cli_dbt` and target `prod`;
- deployer application ID;
- exact stable bundle root:
  `/Workspace/Users/<deployer-application-id>/.bundle/bricks_cli_dbt/prod`;
- source and collector job IDs;
- catalog and resolved observability schema;
- exact staging and evidence Volume IDs under that catalog/schema;
- retention authority, destruction date, approvers, executor, and rollback
  window;
- whether an approved archive export or legal hold is required; and
- the evidence that the independent verifier must retain.

Stop upstream systems from requesting new source runs. Do not pause either job
with a human U2M profile: the one-time M2M workflow below pauses both triggers,
then refuses deletion while either job still has an active run. If it stops at
that gate, wait for the recorded active runs to terminate and dispatch the same
approved workflow again.

Run a final collector sweep only if policy permits, then resolve or explicitly
accept every non-terminal capture and pending cleanup. Do not copy raw artifacts
to an unapproved workstation, repository, or telemetry platform.

Remove routine operator grants after preserving any approved export. During the
approved window, the deployer M2M identity must have `CAN USE` on the configured
SQL warehouse and the Databricks SQL access entitlement where entitlements are
enforced. It also needs authority to drop the eight runtime-created relations
and destroy the bundle-managed resources. Record the complete warehouse ACL and
the deployer's entitlements before an administrator adds that narrow temporary
access; restore both reviewed states after deletion.

## 2. Prepare one reviewed decommission change

Create a dedicated branch and make these three changes in one pull request:

1. delete `.github/workflows/deploy.yml` so merging the guard removal cannot
   trigger the ordinary validate, deploy, source-run, and collector-run path;
2. remove the three `lifecycle.prevent_destroy: true` blocks from the production
   observability schema, staging Volume, and evidence Volume in
   `databricks.yml`; and
3. add the temporary `.github/workflows/decommission-prod.yml` shown below.

Before merging, cancel or finish every queued or running `deploy.yml` run.
Require data-owner and platform/security review, and keep required reviewers on
the GitHub `prod` environment.

!!! warning "Do not deploy after removing the guards"

    Do not run `databricks bundle deploy --target prod`, and do not restore or
    dispatch the ordinary deploy-and-run workflow. The temporary workflow reads
    the existing state at the exact stable root and calls `bundle destroy`
    directly.

Use this temporary workflow exactly once:

```yaml title=".github/workflows/decommission-prod.yml"
name: One-time production deployment and evidence decommission

on:
  workflow_dispatch:
    inputs:
      confirmation:
        description: "Type exactly: DESTROY bricks_cli_dbt prod"
        required: true
        type: string
      expected_root:
        description: "Type the approved, exact production workspace root"
        required: true
        type: string
      expected_catalog:
        description: "Type the approved production catalog from the final-run record"
        required: true
        type: string
      expected_observability_schema:
        description: "Type the approved observability schema from the final-run record"
        required: true
        type: string
      expected_source_job_id:
        description: "Type the approved source job ID from the final-run record"
        required: true
        type: string
      expected_collector_job_id:
        description: "Type the approved collector job ID from the final-run record"
        required: true
        type: string

permissions:
  contents: read

# Reuse the deployment lock even though deploy.yml must be absent.
concurrency: deploy-prod

env:
  DATABRICKS_AUTH_TYPE: oauth-m2m
  DATABRICKS_HOST: ${{ vars.DATABRICKS_HOST }}
  DATABRICKS_CLIENT_ID: ${{ vars.DATABRICKS_CLIENT_ID }}
  BUNDLE_VAR_warehouse_id: ${{ vars.DATABRICKS_WAREHOUSE_ID }}
  BUNDLE_VAR_catalog: ${{ vars.DATABRICKS_CATALOG }}
  BUNDLE_VAR_schema: ${{ vars.DATABRICKS_SCHEMA }}
  BUNDLE_VAR_prod_deployer_service_principal_name: ${{ vars.DATABRICKS_CLIENT_ID }}
  BUNDLE_VAR_prod_run_as_service_principal_name: ${{ vars.DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME }}
  BUNDLE_VAR_prod_collector_service_principal_name: ${{ vars.DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME }}

jobs:
  decommission:
    runs-on: ubuntu-latest
    environment: prod
    env:
      CONFIRMATION: ${{ inputs.confirmation }}
      EXPECTED_ROOT_INPUT: ${{ inputs.expected_root }}
      EXPECTED_CATALOG_INPUT: ${{ inputs.expected_catalog }}
      EXPECTED_OBSERVABILITY_SCHEMA_INPUT: ${{ inputs.expected_observability_schema }}
      EXPECTED_SOURCE_JOB_ID_INPUT: ${{ inputs.expected_source_job_id }}
      EXPECTED_COLLECTOR_JOB_ID_INPUT: ${{ inputs.expected_collector_job_id }}
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7

      - uses: databricks/setup-cli@bc7e6aabb6006d8d1758bd25ee1a100935c9cb7c # v1.7.0
        with:
          version: 1.7.0

      - name: Fail closed before receiving the secret
        shell: bash
        run: |
          set -euo pipefail

          [[ "$GITHUB_REF" == "refs/heads/main" ]] || {
            echo "The one-time workflow must run from main." >&2
            exit 1
          }
          [[ ! -e .github/workflows/deploy.yml ]] || {
            echo "Remove the ordinary production workflow before decommissioning." >&2
            exit 1
          }
          [[ "$CONFIRMATION" == "DESTROY bricks_cli_dbt prod" ]] || {
            echo "Typed confirmation did not match." >&2
            exit 1
          }

          for name in \
            DATABRICKS_HOST \
            DATABRICKS_CLIENT_ID \
            BUNDLE_VAR_warehouse_id \
            BUNDLE_VAR_catalog \
            BUNDLE_VAR_schema \
            BUNDLE_VAR_prod_run_as_service_principal_name \
            BUNDLE_VAR_prod_collector_service_principal_name
          do
            [[ -n "${!name:-}" ]] || {
              echo "Required production input is empty: $name" >&2
              exit 1
            }
          done

          derived_root="/Workspace/Users/${DATABRICKS_CLIENT_ID}/.bundle/bricks_cli_dbt/prod"
          [[ "$EXPECTED_ROOT_INPUT" == "$derived_root" ]] || {
            echo "The typed root does not match the deployer-scoped stable root." >&2
            exit 1
          }

          identifier_re='^[A-Za-z_][A-Za-z0-9_-]{0,127}$'
          for identifier in \
            "$EXPECTED_CATALOG_INPUT" \
            "$EXPECTED_OBSERVABILITY_SCHEMA_INPUT"
          do
            [[ "$identifier" =~ $identifier_re ]] || {
              echo "Unsafe approved Unity Catalog identifier." >&2
              exit 1
            }
          done

          [[ "$EXPECTED_SOURCE_JOB_ID_INPUT" =~ ^[0-9]+$ ]]
          [[ "$EXPECTED_COLLECTOR_JOB_ID_INPUT" =~ ^[0-9]+$ ]]
          [[ "$EXPECTED_SOURCE_JOB_ID_INPUT" != "$EXPECTED_COLLECTOR_JOB_ID_INPUT" ]] || {
            echo "Approved source and collector job IDs must be distinct." >&2
            exit 1
          }

      - name: Drop runtime objects, destroy the bundle, and verify absence
        shell: bash
        env:
          DATABRICKS_CLIENT_SECRET: ${{ secrets.DATABRICKS_CLIENT_SECRET }}
        run: |
          set -euo pipefail

          expected_root="/Workspace/Users/${DATABRICKS_CLIENT_ID}/.bundle/bricks_cli_dbt/prod"

          identity_json="$(databricks current-user me --output json)"
          identity_client_id="$(
            jq -er '.applicationId // .userName' <<< "$identity_json"
          )"
          [[ "$identity_client_id" == "$DATABRICKS_CLIENT_ID" ]] || {
            echo "Authenticated identity is not the approved deployer." >&2
            exit 1
          }

          databricks bundle validate --target prod
          summary="$(databricks bundle summary --target prod --output json)"

          # Refuse to destroy state that owns anything beyond the reviewed
          # two jobs, one schema, and two Volumes.
          jq -e '
            (.resources | keys == ["jobs", "schemas", "volumes"])
            and (.resources.jobs | keys == [
              "dbt_observability_collector_job",
              "nyc_taxi_dbt_job"
            ])
            and (.resources.schemas | keys == ["dbt_observability"])
            and (.resources.volumes | keys == [
              "dbt_artifact_staging",
              "dbt_artifacts"
            ])
          ' <<< "$summary" >/dev/null || {
            echo "Deployed bundle resource set differs from the approved manifest." >&2
            exit 1
          }

          jq -e \
            --arg root "$expected_root" \
            '.bundle.name == "bricks_cli_dbt"
             and .bundle.target == "prod"
             and .bundle.mode == "production"
             and .workspace.root_path == $root
             and ((.resources.schemas.dbt_observability.lifecycle.prevent_destroy // false) == false)
             and ((.resources.volumes.dbt_artifact_staging.lifecycle.prevent_destroy // false) == false)
             and ((.resources.volumes.dbt_artifacts.lifecycle.prevent_destroy // false) == false)' \
            <<< "$summary" >/dev/null

          actual_root="$(jq -er '.workspace.root_path' <<< "$summary")"
          source_job_id="$(
            jq -er '.resources.jobs.nyc_taxi_dbt_job.id' <<< "$summary"
          )"
          collector_job_id="$(
            jq -er '.resources.jobs.dbt_observability_collector_job.id' <<< "$summary"
          )"
          state_schema_id="$(
            jq -er '.resources.schemas.dbt_observability.id' <<< "$summary"
          )"
          resolved_catalog="$(
            jq -er '.resources.schemas.dbt_observability.catalog_name' <<< "$summary"
          )"
          resolved_schema="$(
            jq -er '.resources.schemas.dbt_observability.name' <<< "$summary"
          )"
          state_staging_volume_id="$(
            jq -er '.resources.volumes.dbt_artifact_staging.id' <<< "$summary"
          )"
          state_evidence_volume_id="$(
            jq -er '.resources.volumes.dbt_artifacts.id' <<< "$summary"
          )"

          [[ "$actual_root" == "$expected_root" ]]
          [[ "$source_job_id" == "$EXPECTED_SOURCE_JOB_ID_INPUT" ]] || {
            echo "Source job state does not match the approved job ID." >&2
            exit 1
          }
          [[ "$collector_job_id" == "$EXPECTED_COLLECTOR_JOB_ID_INPUT" ]] || {
            echo "Collector job state does not match the approved job ID." >&2
            exit 1
          }
          catalog="$EXPECTED_CATALOG_INPUT"
          schema="$EXPECTED_OBSERVABILITY_SCHEMA_INPUT"
          expected_schema_id="${catalog}.${schema}"
          expected_staging_volume_id="${catalog}.${schema}.dbt_artifacts_staging"
          expected_evidence_volume_id="${catalog}.${schema}.dbt_artifacts"

          # The resource ID comes from deployed bundle state. The resolved
          # catalog/name come from the reviewed configuration. Requiring all
          # three to equal the separately approved typed inputs prevents a
          # changed repository variable from redirecting the DROP statements.
          [[ "$state_schema_id" == "$expected_schema_id" ]] || {
            echo "Deployed schema state does not match the approved target." >&2
            exit 1
          }
          [[ "$resolved_catalog" == "$catalog" ]] || {
            echo "Resolved catalog does not match the approved target." >&2
            exit 1
          }
          [[ "$resolved_schema" == "$schema" ]] || {
            echo "Resolved schema does not match the approved target." >&2
            exit 1
          }
          [[ "$state_staging_volume_id" == "$expected_staging_volume_id" ]] || {
            echo "Staging Volume state does not match the approved target." >&2
            exit 1
          }
          [[ "$state_evidence_volume_id" == "$expected_evidence_volume_id" ]] || {
            echo "Evidence Volume state does not match the approved target." >&2
            exit 1
          }
          jq -e \
            --arg catalog "$catalog" \
            --arg schema "$schema" \
            '
              .resources.volumes.dbt_artifact_staging as $staging |
              .resources.volumes.dbt_artifacts as $evidence |
              ($staging.catalog_name == $catalog)
              and ($staging.name == "dbt_artifacts_staging")
              and ($evidence.catalog_name == $catalog)
              and ($evidence.name == "dbt_artifacts")
            ' <<< "$summary" >/dev/null || {
              echo "Resolved Volume configuration does not match the approved target." >&2
              exit 1
            }

          source_job="$(databricks jobs get "$source_job_id" --output json)"
          collector_job="$(databricks jobs get "$collector_job_id" --output json)"
          jq -e '.settings.name == "nyc_taxi_dbt_job"' \
            <<< "$source_job" >/dev/null
          jq -e '.settings.name == "nyc_taxi_dbt_observability_collector"' \
            <<< "$collector_job" >/dev/null

          source_update="$(
            jq -cn \
              --argjson job_id "$source_job_id" \
              --argjson trigger \
                "$(jq -c '.settings.trigger + {pause_status: "PAUSED"}' \
                  <<< "$source_job")" \
              '{job_id: $job_id, new_settings: {trigger: $trigger}}'
          )"
          collector_update="$(
            jq -cn \
              --argjson job_id "$collector_job_id" \
              --argjson schedule \
                "$(jq -c '.settings.schedule + {pause_status: "PAUSED"}' \
                  <<< "$collector_job")" \
              '{job_id: $job_id, new_settings: {schedule: $schedule}}'
          )"
          databricks jobs update --json "$source_update"
          databricks jobs update --json "$collector_update"

          databricks jobs get "$source_job_id" --output json |
            jq -e '.settings.trigger.pause_status == "PAUSED"' >/dev/null
          databricks jobs get "$collector_job_id" --output json |
            jq -e '.settings.schedule.pause_status == "PAUSED"' >/dev/null

          for job_id in "$source_job_id" "$collector_job_id"; do
            databricks jobs list-runs \
              --job-id "$job_id" \
              --active-only \
              --limit 1 \
              --output json |
              jq -e 'length == 0' >/dev/null
          done

          {
            echo "## Approved decommission target"
            echo "- Commit: ${GITHUB_SHA}"
            echo "- Root: ${actual_root}"
            echo "- Source job ID: ${source_job_id}"
            echo "- Collector job ID: ${collector_job_id}"
            echo "- Schema: ${catalog}.${schema}"
          } >> "$GITHUB_STEP_SUMMARY"

          run_sql() {
            local statement="$1"
            local payload response

            [[ "$statement" != *CASCADE* ]] || {
              echo "CASCADE is prohibited." >&2
              exit 1
            }
            payload="$(
              jq -cn \
                --arg warehouse_id "$BUNDLE_VAR_warehouse_id" \
                --arg statement "$statement" \
                '{
                  warehouse_id: $warehouse_id,
                  statement: $statement,
                  wait_timeout: "50s",
                  on_wait_timeout: "CANCEL"
                }'
            )"
            response="$(
              databricks api post /api/2.0/sql/statements \
                --json "$payload" \
                --output json
            )"
            jq -e '.status.state == "SUCCEEDED"' <<< "$response" >/dev/null || {
              jq '.status' <<< "$response" >&2
              exit 1
            }
          }

          views=(
            dbt_job_health
            lakeflow_dbt_task_run_health
            lakeflow_job_run_health
            dbt_node_health
            dbt_run_health
          )
          tables=(
            dbt_node_results
            dbt_invocations
            dbt_artifact_registry
          )

          for object in "${views[@]}"; do
            run_sql "DROP VIEW IF EXISTS \`${catalog}\`.\`${schema}\`.\`${object}\`"
          done
          for object in "${tables[@]}"; do
            run_sql "DROP TABLE IF EXISTS \`${catalog}\`.\`${schema}\`.\`${object}\`"
          done

          # No bundle deploy is allowed between guard removal and this destroy.
          databricks bundle destroy --target prod --auto-approve

          databricks jobs list \
            --name nyc_taxi_dbt_job \
            --output json |
            jq -e --argjson id "$source_job_id" \
              'all(.[]; .job_id != $id)' >/dev/null
          databricks jobs list \
            --name nyc_taxi_dbt_observability_collector \
            --output json |
            jq -e --argjson id "$collector_job_id" \
              'all(.[]; .job_id != $id)' >/dev/null
          databricks schemas list "$catalog" --output json |
            jq -e --arg full_name "${catalog}.${schema}" \
              'all(.[]; .full_name != $full_name)' >/dev/null

          user_home="/Workspace/Users/${DATABRICKS_CLIENT_ID}"
          dot_bundle="${user_home}/.bundle"
          bundle_parent="${dot_bundle}/bricks_cli_dbt"
          home_entries="$(databricks workspace list "$user_home" --output json)"
          if jq -e --arg path "$dot_bundle" \
            'any(.[]; .path == $path)' <<< "$home_entries" >/dev/null
          then
            bundle_entries="$(
              databricks workspace list "$dot_bundle" --output json
            )"
            if jq -e --arg path "$bundle_parent" \
              'any(.[]; .path == $path)' <<< "$bundle_entries" >/dev/null
            then
              databricks workspace list "$bundle_parent" --output json |
                jq -e --arg root "$expected_root" \
                  'all(.[]; .path != $root)' >/dev/null
            fi
          fi
```

The workflow has no push trigger, shares the production deployment lock, and
cannot run before `prod` approval releases the deployer secret. Its preflight
checks occur in this order before any deletion:

1. exact `main` ref, absence of `deploy.yml`, typed confirmation, typed root,
   and typed catalog/schema and job IDs from the approved final-run record;
2. deployer M2M identity and exact bundle name, target, mode, and stable root;
3. reviewed removal of all three lifecycle guards;
4. an exact two-job, one-schema, two-Volume resource set, with job IDs, schema
   ID, Volume IDs, and resolved configuration all matching the separately
   approved inputs; and
5. both triggers paused by the deployer M2M identity, with no active runs.

Only then does it drop exactly five views followed by three tables, without
`CASCADE`, and run `bundle destroy` as the deployer.

## 3. Merge and run once

Merge the reviewed change to `main`. Because that commit removes `deploy.yml`,
the guard removal must not start a normal deployment or either production job.

Dispatch the temporary workflow with every exact approved input:

```bash
export DEPLOYER_APPLICATION_ID="<approved-deployer-application-id>"
export EXPECTED_ROOT="/Workspace/Users/${DEPLOYER_APPLICATION_ID}/.bundle/bricks_cli_dbt/prod"
export EXPECTED_CATALOG="<catalog-recorded-with-the-final-run>"
export EXPECTED_OBSERVABILITY_SCHEMA="<observability-schema-recorded-with-the-final-run>"
export EXPECTED_SOURCE_JOB_ID="<source-job-id-recorded-with-the-final-run>"
export EXPECTED_COLLECTOR_JOB_ID="<collector-job-id-recorded-with-the-final-run>"

gh workflow run decommission-prod.yml \
  --ref main \
  -f confirmation='DESTROY bricks_cli_dbt prod' \
  -f expected_root="$EXPECTED_ROOT" \
  -f expected_catalog="$EXPECTED_CATALOG" \
  -f expected_observability_schema="$EXPECTED_OBSERVABILITY_SCHEMA" \
  -f expected_source_job_id="$EXPECTED_SOURCE_JOB_ID" \
  -f expected_collector_job_id="$EXPECTED_COLLECTOR_JOB_ID"
```

Approve the `prod` environment only after comparing the workflow commit, typed
root, typed catalog/schema and job IDs, change record, and final-run evidence.
Do not derive the typed catalog/schema or job IDs from the mutable repository
variables/state in the decommission commit. Watch the selected run to its
terminal result:

```bash
gh run list --workflow decommission-prod.yml --limit 1
gh run watch <run-id> --exit-status
```

The run must succeed before the change is called complete. Preserve its URL and
step summary in the change record.

## 4. Verify independently

A different approver must verify absence with an authoritative audit identity:
workspace/job administrator for complete job enumeration, metastore
administrator or parent-catalog owner for complete schema enumeration, and
visibility on the deployer workspace home for directory enumeration. A routine
operator profile is insufficient because list APIs can omit resources the
caller cannot see.

Use the job IDs, catalog, schema, and root recorded before destruction:

```bash
set -euo pipefail
export REVIEWER_PROFILE="<independent-reviewer-profile>"
export SOURCE_JOB_ID="<recorded-source-job-id>"
export COLLECTOR_JOB_ID="<recorded-collector-job-id>"
export CATALOG="<recorded-catalog>"
export OBSERVABILITY_SCHEMA="<recorded-observability-schema>"
export DEPLOYER_APPLICATION_ID="<recorded-deployer-application-id>"
export USER_HOME="/Workspace/Users/${DEPLOYER_APPLICATION_ID}"
export DOT_BUNDLE="${USER_HOME}/.bundle"
export BUNDLE_PARENT="${DOT_BUNDLE}/bricks_cli_dbt"
export EXPECTED_ROOT="${BUNDLE_PARENT}/prod"

databricks jobs list \
  --name nyc_taxi_dbt_job \
  --profile "$REVIEWER_PROFILE" \
  --output json |
  jq -e --argjson id "$SOURCE_JOB_ID" \
    'all(.[]; .job_id != $id)' >/dev/null
databricks jobs list \
  --name nyc_taxi_dbt_observability_collector \
  --profile "$REVIEWER_PROFILE" \
  --output json |
  jq -e --argjson id "$COLLECTOR_JOB_ID" \
    'all(.[]; .job_id != $id)' >/dev/null
databricks schemas list "$CATALOG" \
  --profile "$REVIEWER_PROFILE" \
  --output json |
  jq -e --arg full_name "${CATALOG}.${OBSERVABILITY_SCHEMA}" \
    'all(.[]; .full_name != $full_name)' >/dev/null

home_entries="$(
  databricks workspace list "$USER_HOME" \
    --profile "$REVIEWER_PROFILE" \
    --output json
)"
if jq -e --arg path "$DOT_BUNDLE" \
  'any(.[]; .path == $path)' <<< "$home_entries" >/dev/null
then
  bundle_entries="$(
    databricks workspace list "$DOT_BUNDLE" \
      --profile "$REVIEWER_PROFILE" \
      --output json
  )"
  if jq -e --arg path "$BUNDLE_PARENT" \
    'any(.[]; .path == $path)' <<< "$bundle_entries" >/dev/null
  then
    databricks workspace list "$BUNDLE_PARENT" \
      --profile "$REVIEWER_PROFILE" \
      --output json |
      jq -e --arg root "$EXPECTED_ROOT" \
        'all(.[]; .path != $root)' >/dev/null
  fi
fi
```

Each list command must succeed, each `jq -e` assertion must return true, and the
change record must prove the verifier held the authoritative roles above.
Without that role evidence, an empty filtered list is inconclusive. With it,
the missing observability schema proves that its three tables, five views, and
both managed Volumes are absent. Independently confirm that the parent catalog,
SQL warehouse, and unrelated jobs still exist.

## 5. Remove the one-time path, external grants, and credentials

After independent verification, make the temporary workflow unusable before
doing anything else:

```bash
gh secret delete DATABRICKS_CLIENT_SECRET --env prod
```

Immediately merge a cleanup pull request that removes
`.github/workflows/decommission-prod.yml`. Keep the ordinary `deploy.yml`
workflow removed. Remove the retired production configuration, or restore all
three lifecycle guards before retaining it as reference; never leave an
unguarded `prod` target ready for deployment.

Delete repository variables that were dedicated to this workload:

```bash
for name in \
  DATABRICKS_CLIENT_ID \
  DATABRICKS_WAREHOUSE_ID \
  DATABRICKS_CATALOG \
  DATABRICKS_SCHEMA \
  DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME \
  DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME \
  DATABRICKS_NOTIFICATION_EMAILS
do
  gh variable delete "$name"
done
```

Delete `DATABRICKS_HOST` too only if no other repository workflow uses it. Keep
the GitHub environment and deployment history for the required audit-retention
period.

Have the warehouse administrator remove the deployer's temporary `CAN USE`
entry and compare the complete effective ACL with the recorded pre-change ACL.
Preserve unrelated direct entries and inspect group-inherited access separately.
Remove the temporary Databricks SQL access entitlement too, where the workspace
exposes entitlement management, and verify the deployer returned to its
pre-change entitlement set.

`bundle destroy` does not revoke prerequisites on external resources. Through a
separately reviewed administrator change, remove every workload-specific grant
that was introduced by the prerequisite guide:

- runner direct `CAN USE` on the SQL warehouse;
- deployer Service Principal User on both runtime principals;
- deployer `USE CATALOG` / `CREATE SCHEMA` on the parent catalog;
- runner catalog and dbt-target schema privileges;
- collector `USE CATALOG` on the parent catalog; and
- optional collector access to `system.lakeflow`.

Revoke the Unity Catalog grants that were dedicated to this workload:

```sql
REVOKE USE CATALOG, CREATE SCHEMA
ON CATALOG `<production-catalog>`
FROM `<deployer-application-id>`;

REVOKE USE CATALOG
ON CATALOG `<production-catalog>`
FROM `<runner-application-id>`;
REVOKE USE SCHEMA, CREATE TABLE, SELECT, MODIFY
ON SCHEMA `<production-catalog>`.`<production-dbt-schema>`
FROM `<runner-application-id>`;

REVOKE USE CATALOG
ON CATALOG `<production-catalog>`
FROM `<collector-application-id>`;

-- Run these only when optional enrichment was granted.
REVOKE SELECT
ON TABLE `system`.`lakeflow`.`job_task_run_timeline`
FROM `<collector-application-id>`;
REVOKE SELECT
ON TABLE `system`.`lakeflow`.`job_run_timeline`
FROM `<collector-application-id>`;
REVOKE USE SCHEMA
ON SCHEMA `system`.`lakeflow`
FROM `<collector-application-id>`;
REVOKE USE CATALOG
ON CATALOG `system`
FROM `<collector-application-id>`;
```

Use the SQL warehouse Permissions UI to remove only the recorded direct runner
and temporary deployer entries; then use `databricks permissions get
warehouses <warehouse-id>` to compare the complete ACL with the approved
post-decommission state. In workspace service-principal settings, remove the
deployer's Service Principal User role from runner and collector.

Run `SHOW GRANTS` for every catalog, schema, and table listed above and inspect
group membership. A missing direct row is insufficient when an inherited group still
provides the same capability. Preserve any grant proved to be shared with an
unrelated approved workload and record that exception instead of revoking it
blindly.

Using an approved human administrator profile, list and revoke every remaining
OAuth secret created for the dedicated deployer:

```bash
databricks service-principal-secrets-proxy list \
  <deployer-numeric-service-principal-id> \
  --profile <admin-profile> \
  --output json

databricks service-principal-secrets-proxy delete \
  <deployer-numeric-service-principal-id> \
  <secret-id> \
  --profile <admin-profile>
```

After confirming that the deployer, runner, and collector serve no other
workload, disable them according to identity policy and delete them only after
the rollback and audit-retention windows close. Record secret revocation,
identity disposition, GitHub cleanup, workflow removal, and independent
verification in the closed change.

## Failure handling

- If any preflight check fails, correct the reviewed inputs or pause state; do
  not weaken the gate.
- If a `DROP` statement fails, the workflow stops before `bundle destroy`.
  Preserve the error, repair only the missing authority or warehouse condition,
  and rerun the approved one-time workflow. `IF EXISTS` makes completed drops
  safe to repeat.
- If `bundle destroy` partially fails, keep both deployment workflows disabled,
  preserve the stable root and logs, inspect bundle state, and rerun destruction
  only after renewed approval.
- Never recover by running `bundle deploy`, adding `CASCADE`, deleting bundle
  state by hand, or using a human token for destruction.

Decommissioning is complete only when the one-time workflow and independent
verification both prove absence, unrelated resources remain, the temporary
workflow and production credential are gone, dedicated identities are disposed
according to policy, and the change record is closed.
