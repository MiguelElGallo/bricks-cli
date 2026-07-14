---
icon: lucide/shield-plus
---

# Grant production prerequisites

Give the deployer, source runner, and collector only the access they need before
the first protected production deployment.

After this guide:

- the deployer can assign both production `run_as` identities and create the
  bundle's governed objects;
- the runner can use one SQL warehouse and build only in the dbt target schema;
- the collector can reach the parent catalog without gaining access to the dbt
  target schema; and
- optional `system.lakeflow` access is limited to the two tables the collector
  reads.

!!! danger "Free Edition is validation only"

    These grants make the reference deployment functionally testable. They do
    not make AWS Databricks Free Edition suitable for regulated production.
    Free Edition has no compliance enforcement, private networking, account
    console, account-level APIs, SLA, or support commitment. See the official
    [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations).

## Before you begin

You need:

- an administrator OAuth U2M profile for the target workspace;
- three active, distinct workspace service principals: deployer, runner, and
  collector;
- each service principal's application ID and numeric workspace ID;
- `CAN MANAGE` on the SQL warehouse;
- authority to grant on the production catalog and dbt schema; and
- `jq` for the CLI checks.

Set shell variables once. Keep OAuth secrets out of these variables:

```bash
export ADMIN_PROFILE="<workspace-admin-u2m-profile>"
export WAREHOUSE_ID="<sql-warehouse-id>"
export CATALOG="<production-catalog>"
export DBT_SCHEMA="<production-dbt-schema>"

export DEPLOYER_APPLICATION_ID="<deployer-application-id>"
export RUNNER_APPLICATION_ID="<runner-application-id>"
export COLLECTOR_APPLICATION_ID="<collector-application-id>"

export DEPLOYER_NUMERIC_ID="<deployer-numeric-workspace-id>"
export RUNNER_NUMERIC_ID="<runner-numeric-workspace-id>"
export COLLECTOR_NUMERIC_ID="<collector-numeric-workspace-id>"
```

## 1. Confirm workspace membership

Each principal must be active in the workspace. This check uses the numeric
workspace IDs, not the application IDs used by `run_as` and Unity Catalog:

```bash
jq -ne \
  --arg deployer "$DEPLOYER_APPLICATION_ID" \
  --arg runner "$RUNNER_APPLICATION_ID" \
  --arg collector "$COLLECTOR_APPLICATION_ID" \
  '
    $deployer != $runner and
    $deployer != $collector and
    $runner != $collector
  '

for id in \
  "$DEPLOYER_NUMERIC_ID" \
  "$RUNNER_NUMERIC_ID" \
  "$COLLECTOR_NUMERIC_ID"
do
  databricks service-principals get "$id" \
    --profile "$ADMIN_PROFILE" \
    --output json |
    jq -e '.active == true'
done
```

The identity check and all three membership checks must print `true`. An account
or workspace administrator can assign service principals to a workspace; see
[Manage service principals](https://docs.databricks.com/aws/en/admin/users-groups/manage-service-principals).

## 2. Let the deployer use both runtime identities

Grant the deployer **Service principal: User** on the runner and collector:

1. Open the workspace as an administrator.
2. Select **Settings > Identity and access > Service principals > Manage**.
3. Open the runner, then its **Permissions** tab.
4. Grant the deployer service principal **Service principal: User**.
5. Repeat for the collector.

The operator making this change must have **Service Principal Manager** on each
runtime principal. Manager does not imply User; the use role must be explicit.

### Why the role appears in workspace settings

Service Principal User is an account-level role: it is defined once and applies
across workspaces. Databricks nevertheless exposes it through workspace admin
settings for workspace administrators who are managers of the selected service
principal. The UI label is **Service principal: User**, the role API name is
`roles/servicePrincipal.user`, the workspace filter is
`servicePrincipal/use`, and bundle documentation describes the capability as
`CAN_USE` on the service principal.

This is not the SQL warehouse `CAN_USE` ACL granted in the next sections. The
two permissions protect different resources.

Free Edition has no account console or account-level APIs. Use the workspace
settings route above; the role remains account-scoped even though it is managed
through the workspace. This limitation is caused by the Free Edition product
boundary, not by the personal email address or by OAuth U2M/M2M. See
[Roles for managing service principals](https://docs.databricks.com/aws/en/security/auth/access-control/service-principal-acl)
and [bundle run identity](https://docs.databricks.com/aws/en/dev-tools/bundles/run-as).

## 3. Assign only the required workspace entitlements

In workspaces that expose entitlement management, assign:

| Principal | Required entitlement |
|---|---|
| Deployer | Workspace access |
| Runner | Workspace access and Databricks SQL access |
| Collector | Workspace access |

Do not grant **Allow unrestricted cluster creation** or **Allow pool creation**
for this bundle. The source uses a SQL warehouse and the collector uses
serverless jobs; neither principal creates classic compute or pools.

Verify explicit entitlements where they are available:

```bash
for id in "$DEPLOYER_NUMERIC_ID" "$COLLECTOR_NUMERIC_ID"
do
  databricks service-principals get "$id" \
    --profile "$ADMIN_PROFILE" \
    --output json |
    jq -e '
      .active == true and
      ([.entitlements[]?.value] | index("workspace-access") != null)
    '
done

databricks service-principals get "$RUNNER_NUMERIC_ID" \
  --profile "$ADMIN_PROFILE" \
  --output json |
  jq -e '
    .active == true and
    ([.entitlements[]?.value] | index("workspace-access") != null) and
    ([.entitlements[]?.value] | index("databricks-sql-access") != null)
  '

for id in \
  "$DEPLOYER_NUMERIC_ID" \
  "$RUNNER_NUMERIC_ID" \
  "$COLLECTOR_NUMERIC_ID"
do
  databricks service-principals get "$id" \
    --profile "$ADMIN_PROFILE" \
    --output json |
    jq -e '
      [
        .entitlements[]?.value |
        select(
          . == "allow-cluster-create" or
          . == "allow-instance-pool-create"
        )
      ] | length == 0
    '
done
```

Databricks is changing how new workspace principals inherit entitlements, so do
not rely on membership in the `users` system group. See
[Manage entitlements](https://docs.databricks.com/aws/en/security/auth/entitlements).

Free Edition might not expose the Premium entitlement controls. In that case,
the `.active` membership check still applies, serverless availability is a
product capability, and the protected job run is the functional verification.
An absent entitlement UI is not evidence of enterprise-grade access control.

## 4. Grant the runner warehouse `CAN_USE`

Add one direct warehouse ACL without replacing unrelated approved entries:

```bash
warehouse_acl="$(
  jq -cn \
    --arg runner "$RUNNER_APPLICATION_ID" \
    '{
      access_control_list: [
        {
          service_principal_name: $runner,
          permission_level: "CAN_USE"
        }
      ]
    }'
)"

databricks permissions update \
  warehouses "$WAREHOUSE_ID" \
  --profile "$ADMIN_PROFILE" \
  --json "$warehouse_acl"
```

`CAN_USE` lets the runner connect and execute dbt queries. It does not allow the
runner to manage warehouse settings. The deployer and collector do not need a
warehouse ACL for this project. See the official
[permissions CLI](https://docs.databricks.com/aws/en/dev-tools/cli/reference/permissions-commands)
and [SQL warehouse access guidance](https://docs.databricks.com/aws/en/sql/user/sql-editor/write-queries).

## 5. Grant the external Unity Catalog prerequisites

Run the following in a Databricks SQL editor as the catalog/schema owner, a
principal with the required `MANAGE` authority, or a metastore administrator.
Replace every placeholder before execution.

```sql
-- The deployer creates the bundle-owned observability schema.
GRANT USE CATALOG, CREATE SCHEMA
ON CATALOG `<production-catalog>`
TO `<deployer-application-id>`;

-- The runner builds the seed and table and executes dbt tests.
GRANT USE CATALOG
ON CATALOG `<production-catalog>`
TO `<runner-application-id>`;

GRANT USE SCHEMA, CREATE TABLE, SELECT, MODIFY
ON SCHEMA `<production-catalog>`.`<production-dbt-schema>`
TO `<runner-application-id>`;

-- The collector needs the parent catalog before the bundle-created schema exists.
GRANT USE CATALOG
ON CATALOG `<production-catalog>`
TO `<collector-application-id>`;
```

These are the prerequisites for resources outside the bundle. During deployment,
`databricks.yml` grants the runner `USE SCHEMA` plus staging Volume access, and
grants the collector its observability-schema and both-Volume privileges. Do not
duplicate those target-scoped grants manually.

Use a dedicated dbt target schema. If the resolved observability schema already
exists under a different owner, stop and reconcile ownership with the bundle
before deployment; do not compensate with catalog-wide `ALL PRIVILEGES`.

Unity Catalog requires `USE CATALOG` and `USE SCHEMA` in addition to the
operation-specific privilege. Schema-level `SELECT` and `MODIFY` apply to current
and future objects in that dbt schema. See
[Manage Unity Catalog privileges](https://docs.databricks.com/aws/en/data-governance/unity-catalog/manage-privileges)
and the [privileges reference](https://docs.databricks.com/aws/en/data-governance/unity-catalog/access-control/privileges-reference).

## 6. Optionally grant two Lakeflow system tables

Skip this section when system-table enrichment is not approved. Canonical dbt
artifact capture and the two guaranteed dbt views do not depend on it.

For the narrowest supported grant, allow only the two tables the collector
reads:

```sql
GRANT USE CATALOG
ON CATALOG `system`
TO `<collector-application-id>`;

GRANT USE SCHEMA
ON SCHEMA `system`.`lakeflow`
TO `<collector-application-id>`;

GRANT SELECT
ON TABLE `system`.`lakeflow`.`job_run_timeline`
TO `<collector-application-id>`;

GRANT SELECT
ON TABLE `system`.`lakeflow`.`job_task_run_timeline`
TO `<collector-application-id>`;
```

Do not grant `SELECT ON SCHEMA system.lakeflow` unless access to every current
and future table in that schema is approved. System tables contain account
operational metadata and can lag; see the official
[system tables reference](https://docs.databricks.com/aws/en/admin/system-tables/).

## 7. Verify the external prerequisites

### Verify the direct warehouse ACL

```bash
databricks permissions get \
  warehouses "$WAREHOUSE_ID" \
  --profile "$ADMIN_PROFILE" \
  --output json |
  jq -e \
    --arg runner "$RUNNER_APPLICATION_ID" \
    '
      [
        .access_control_list[]? |
        select(.service_principal_name == $runner) |
        .all_permissions[]?.permission_level
      ] as $levels |
      ($levels | index("CAN_USE") != null) and
      ($levels | index("CAN_MANAGE") == null)
    '
```

The command must print `true`.

### Verify Unity Catalog grants

Run these statements as an owner, administrator, or principal permitted to view
the grants:

```sql
SHOW GRANTS `<deployer-application-id>`
ON CATALOG `<production-catalog>`;

SHOW GRANTS `<runner-application-id>`
ON CATALOG `<production-catalog>`;

SHOW GRANTS `<runner-application-id>`
ON SCHEMA `<production-catalog>`.`<production-dbt-schema>`;

SHOW GRANTS `<collector-application-id>`
ON CATALOG `<production-catalog>`;
```

Require exactly the capabilities granted in section 5, allowing for approved
inherited grants. If optional enrichment is enabled, verify it explicitly:

```sql
SHOW GRANTS `<collector-application-id>`
ON CATALOG `system`;

SHOW GRANTS `<collector-application-id>`
ON SCHEMA `system`.`lakeflow`;

SHOW GRANTS `<collector-application-id>`
ON TABLE `system`.`lakeflow`.`job_run_timeline`;

SHOW GRANTS `<collector-application-id>`
ON TABLE `system`.`lakeflow`.`job_task_run_timeline`;
```

Require `USE CATALOG`, `USE SCHEMA`, and table-level `SELECT` on both tables.

## 8. Verify the negative boundary

First inspect every warehouse entry, including groups and inherited grants:

```bash
databricks permissions get \
  warehouses "$WAREHOUSE_ID" \
  --profile "$ADMIN_PROFILE" \
  --output json |
  jq '.access_control_list[]? | {
    user_name,
    group_name,
    service_principal_name,
    all_permissions
  }'
```

Then assert that there is no direct warehouse grant for the deployer or
collector and no direct `CAN_MANAGE` for the runner:

```bash
databricks permissions get \
  warehouses "$WAREHOUSE_ID" \
  --profile "$ADMIN_PROFILE" \
  --output json |
  jq -e \
    --arg deployer "$DEPLOYER_APPLICATION_ID" \
    --arg runner "$RUNNER_APPLICATION_ID" \
    --arg collector "$COLLECTOR_APPLICATION_ID" \
    '
      ([
        .access_control_list[]? |
        select(
          .service_principal_name == $deployer or
          .service_principal_name == $collector
        )
      ] | length == 0) and
      ([
        .access_control_list[]? |
        select(.service_principal_name == $runner) |
        .all_permissions[]? |
        select(.permission_level == "CAN_MANAGE")
      ] | length == 0)
    '
```

The command must print `true`. This assertion covers direct service-principal
entries. Trace every group entry from the preceding output because group
membership can still confer broader effective access.

Before the first deployment, use `SHOW GRANTS` to prove the external data
boundary:

```sql
-- Collector: no dbt target-schema data role.
SHOW GRANTS `<collector-application-id>`
ON SCHEMA `<production-catalog>`.`<production-dbt-schema>`;

```

Fail the review if the collector has `USE SCHEMA`, `CREATE TABLE`, `SELECT`, or
`MODIFY` on the dbt target schema. Include inherited catalog, schema, and group
grants in the decision. The production verification guide checks the
bundle-created Volumes and runtime tables after they exist.

If a Free Edition default or inherited group grant cannot be narrowed, record it
as a platform limitation. Do not present the personal validation workspace as
proof of regulated least privilege.

## Success criteria

Prerequisites are complete when:

- the three active service principals are pairwise distinct;
- the deployer has been granted Service Principal User on both runtime
  principals;
- the runner has direct warehouse `CAN_USE`, not `CAN_MANAGE`;
- the external Unity Catalog grants match section 5;
- no forbidden external direct or inherited grant defeats the separation
  boundary; and
- optional system-table access is either absent or limited to the approved
  `system.lakeflow` objects.

Return to
[Check configuration metadata](set-up-m2m-cicd.md#6-check-configuration-metadata)
in the M2M setup guide. The protected deployment workflow itself proves that
the deployer can use both runtime principals; production verification owns all
post-deployment Volume, table, job, and ACL checks. Use
[Permissions](../reference/permissions.md) as the complete role and resource
matrix.
