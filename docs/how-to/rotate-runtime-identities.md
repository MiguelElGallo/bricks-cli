---
icon: lucide/users-round
---

# Rotate the runtime identities

Replace the source-runner and collector service principals without losing
access to staged or canonical evidence.

Runtime identities do not need OAuth client secrets for `run_as`. Rotation is
an authorization and ownership change, not a deployer-secret rotation.

## Prerequisites

You need:

- new runner and collector service principals with workspace access;
- authority to grant workspace, job, warehouse, and Unity Catalog permissions;
- authority to transfer ownership of runtime-created tables and views,
  including metastore-admin involvement when a view is transferred to a
  different service principal;
- the old and new application IDs; and
- a recent successful production verification.

Do not remove the old principals before the new collector can read existing
state and update every existing view.

## 1. Prepare the new runner

Grant only the runner prerequisites that exist outside the bundle:

- workspace access and Databricks SQL access where entitlements are enforced;
- `CAN_USE` on the SQL warehouse;
- `USE CATALOG` and `USE SCHEMA` on the dbt target;
- the target object privileges required by the dbt materializations;
- `USE CATALOG` on the observability parent catalog; and
- Service Principal User for the deployer on the new runner.

Do not grant it evidence Volume or observability base-table access.

The reviewed bundle deployment later grants observability-schema `USE SCHEMA`
and staging-Volume access; the protected workflow replaces the deployed-file
ACL with runner `CAN_READ`. Do not pre-grant those bundle-owned permissions.

## 2. Prepare the new collector

Grant only the collector prerequisites that exist outside the bundle:

- workspace and serverless job access;
- `USE CATALOG` on the parent catalog;
- Service Principal User for the deployer on the new collector; and
- optional read access to `system.lakeflow` if those views are approved.

The reviewed bundle deployment grants collector `CAN_VIEW` on the source job,
observability-schema privileges, and both Volume ACLs. The protected workflow
replaces the deployed-file ACL with collector `CAN_RUN`. Keeping those mutations
inside the bundle/workflow prevents a second, conflicting authorization path.

## 3. Freeze recurring production triggers

Pause both schedules through the protected deployer M2M identity before
changing ownership:

```bash
gh workflow run deploy.yml --ref main -f operation=freeze
```

Approve the `prod` environment and wait for **Freeze recurring triggers
(prod)** to succeed. The operation preserves each trigger definition, changes
only `pause_status`, and fails closed if either job still has an active run.
When it succeeds, record the workflow URL and job IDs.

Do not continue while an old-identity source or collector run is active. Keep
both triggers paused throughout the ownership and variable changes.

## 4. Transfer runtime-created object ownership

Both runtime identities own objects that they create. Schema privileges alone
do not guarantee that a replacement principal can run `CREATE OR REPLACE` or
alter an object owned by its predecessor.

### Transfer dbt target relations

Inspect every relation managed by the project in the production dbt schema.
For the committed graph, transfer both seeds, the two tables, and the view to
the new runner:

```sql
ALTER TABLE `<catalog>`.`<dbt-schema>`.`nyc_taxi_trips_seed`
  OWNER TO `<new-runner-principal>`;
ALTER TABLE `<catalog>`.`<dbt-schema>`.`nyc_taxi_trips`
  OWNER TO `<new-runner-principal>`;
ALTER TABLE `<catalog>`.`<dbt-schema>`.`weather_daily_seed`
  OWNER TO `<new-runner-principal>`;
ALTER VIEW `<catalog>`.`<dbt-schema>`.`weather_daily_observations`
  OWNER TO `<new-runner-principal>`;
ALTER TABLE `<catalog>`.`<dbt-schema>`.`weather_station_summary`
  OWNER TO `<new-runner-principal>`;
```

If the graph has changed, use the reviewed dbt manifest and Catalog Explorer to
enumerate all additional dbt-managed relations before proceeding. A stable
owner group is acceptable only when the new runner is an authorized member and
the broader edit surface is approved.

### Transfer observability relations

The collector creates and replaces Delta tables and views at run time. A new
collector may have schema privileges but still be unable to replace an object
owned by the former principal.

Inspect current ownership in Catalog Explorer or through `DESCRIBE EXTENDED`.
Transfer each existing object to the new collector. Unity Catalog places
stricter controls on view ownership than ordinary grants: transferring a view
to another service principal generally requires a metastore admin.

An approved stable operations group is an alternative only when the new and
future collector principals are authorized members of that group and the
resulting collaborative edit surface is acceptable. A collector that is not a
member of the owner group may be unable to replace the view.

```sql
ALTER TABLE `<catalog>`.`<observability-schema>`.`dbt_artifact_registry`
  OWNER TO `<new-collector-principal>`;
ALTER TABLE `<catalog>`.`<observability-schema>`.`dbt_invocations`
  OWNER TO `<new-collector-principal>`;
ALTER TABLE `<catalog>`.`<observability-schema>`.`dbt_node_results`
  OWNER TO `<new-collector-principal>`;

ALTER VIEW `<catalog>`.`<observability-schema>`.`dbt_run_health`
  OWNER TO `<new-collector-principal>`;
ALTER VIEW `<catalog>`.`<observability-schema>`.`dbt_node_health`
  OWNER TO `<new-collector-principal>`;
```

Transfer the three optional views too if they exist:

```sql
ALTER VIEW `<catalog>`.`<observability-schema>`.`lakeflow_job_run_health`
  OWNER TO `<new-collector-principal>`;
ALTER VIEW `<catalog>`.`<observability-schema>`.`lakeflow_dbt_task_run_health`
  OWNER TO `<new-collector-principal>`;
ALTER VIEW `<catalog>`.`<observability-schema>`.`dbt_job_health`
  OWNER TO `<new-collector-principal>`;
```

Use principal names exactly as Unity Catalog resolves them. Ownership transfer
is privileged and should be recorded.

## 5. Update the protected deployment inputs

Update both repository variables:

```bash
gh variable set DATABRICKS_RUN_AS_SERVICE_PRINCIPAL_NAME \
  --body "<new-runner-application-id>"

gh variable set DATABRICKS_COLLECTOR_SERVICE_PRINCIPAL_NAME \
  --body "<new-collector-application-id>"
```

The deployer must have Databricks `CAN_USE` on both new principals before it
can assign them as `run_as`.

## 6. Deploy and reconcile ACLs

Trigger the protected production workflow:

```bash
gh workflow run deploy.yml --ref main -f operation=deploy
```

After approval, the workflow deploys both new `run_as` values and uses
`permissions set` to replace every direct deployed-directory entry with:

- new runner `CAN_READ`; and
- new collector `CAN_RUN`.

It then runs the source and two collector sweeps as the new identities. The
reviewed bundle deployment also restores the configured production trigger
states, including the unpaused collector schedule.

## 7. Verify before retiring the old principals

Complete
[Verify a production deployment](verify-production-deployment.md). In
particular, prove:

- each job reports the new `run_as` principal;
- the collector can merge into all three base tables;
- guaranteed views are refreshed;
- optional views refresh when their grants exist;
- a new attempt becomes `COMPLETE`; and
- rerunning the collector remains idempotent.

Audit the schema, Volumes, jobs, warehouse, target schema, and workspace
directory for grants to the old identities.

## 8. Retire the old access

After successful verification:

1. verify with `permissions get` that the old application IDs have no direct
   workspace-directory entry (the workflow replacement should already have
   removed them);
2. remove old job, warehouse, schema, table, and Volume grants;
3. remove optional system-table access;
4. remove obsolete `CAN_USE` assignments on the old service principals; and
5. disable the old service principals only after confirming they serve no other
   workload.

Do not delete evidence or transfer it back to the source runner.

## Success criteria

Rotation is complete when only the new runtime principals retain required
access, existing evidence remains queryable, new evidence becomes `COMPLETE`,
and the old principals have no residual route to staging, evidence, or deployed
files.

## Recovery

If rotation fails after the freeze, leave both triggers paused while repairing
the issue. If deployment fails before the bundle changes, restore the previous
repository variables and dispatch `operation=deploy` to restore the old
identities and configured trigger states.

If the new collector cannot update existing objects, restore ownership to the
old collector or approved operations group, restore the old collector variable,
redeploy, and retry the ownership plan.

If the new runner fails, restore only the runner variable while leaving the
working collector in place, and restore target-relation ownership to the old
runner or approved owner group before dispatching the rollback deployment.
Avoid rotating both roles again until the failed layer is understood.

Never recover by granting the runner broad evidence access or making both jobs
run as the deployer.
