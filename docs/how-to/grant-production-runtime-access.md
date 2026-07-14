---
icon: lucide/folder-key
---

# Repair production runtime file access

Use this recovery guide when the source runner cannot read the deployed dbt
project or the collector cannot execute its deployed notebook.

The normal production workflow already replaces the bundle directory's direct
ACL after every deployment. Do not run a second manual grant after a successful
workflow.

## What the workflow enforces

Production code is deployed beneath the deployer service principal's stable
workspace home. The workflow preserves inherited administrator/deployer access
and replaces every direct entry with exactly:

| Runtime identity | Direct permission |
|---|---|
| Source runner | `CAN_READ` |
| Collector | `CAN_RUN` |

Replacement is intentional: it removes a rotated or mistyped runtime identity
instead of leaving residual access.

## 1. Inspect the current ACL without changing it

You need a U2M profile with permission to view workspace-directory ACLs, GitHub
read access, and `jq`.

Read the non-secret deployer application ID from the approved repository
variable and construct the stable path declared in `databricks.yml`:

```bash
deployer="$(gh variable get DATABRICKS_CLIENT_ID)"
bundle_files="/Workspace/Users/${deployer}/.bundle/bricks_cli_dbt/prod/files"
object_id="$(
  databricks workspace get-status \
    "$bundle_files" \
    --profile bricks-demo \
    --output json |
    jq -er '.object_id'
)"

databricks permissions get \
  directories "$object_id" \
  --profile bricks-demo \
  --output json
```

Stop if the object lookup fails. Do not guess another production root. Confirm
whether the two intended application IDs are present and whether an obsolete
direct principal remains.

## 2. Correct the approved inputs or authority

- If an application ID is wrong, correct
  `DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME` or
  `DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME` in GitHub.
- If the deployer cannot update the directory, repair its authority on the
  stable bundle root. Do not grant that authority to a runtime identity.
- If the ACL is correct, check the job `run_as`, warehouse, and Unity Catalog
  layers before changing it.

Use [Grant production prerequisites](grant-production-prerequisites.md) for the
external permission checks.

## 3. Reconcile through the protected workflow

Trigger the reviewed `main` workflow:

```bash
gh workflow run deploy.yml --ref main -f operation=deploy
```

Approve the `prod` environment. The M2M deployer resolves the deployed
directory from its own bundle state and calls `permissions set`, which replaces
all direct entries with the intended runner and collector ACL.

Do not paste the deployer secret into a local profile and do not use a human U2M
identity to mutate production.

## 4. Verify repair

After the workflow succeeds, repeat the read-only `permissions get` call. Check:

- the runner has `CAN_READ` and no edit/manage permission;
- the collector has `CAN_RUN` and no edit/manage permission;
- old runtime application IDs have no direct entry; and
- inherited deployer/administrator access remains visible where applicable.

Then complete [Verify a production deployment](verify-production-deployment.md).
The workflow's source run and two collector sweeps are the acceptance test.

## Recovery

If ACL reconciliation still fails, preserve the failed workflow logs, repair
only the deployer's directory-management authority, and rerun the protected
workflow. Do not work around the failure with `CAN_MANAGE` for either runtime
identity.

If file access succeeds but a job still fails, inspect these independent
layers:

1. job permission and `run_as`;
2. workspace and compute entitlement;
3. SQL warehouse `CAN USE`; and
4. Unity Catalog grants.

The directory ACL cannot compensate for a missing permission in another
layer.
