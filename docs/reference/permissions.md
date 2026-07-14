---
icon: lucide/shield-check
---

# Permissions

Production separates deployment, dbt execution, evidence collection, and
routine observation. Bundle-declared grants do not replace the external
workspace, compute, parent-catalog, or service-principal prerequisites.

## Principal matrix

| Principal | Purpose | Must not receive |
|-----------|---------|------------------|
| Deployer service principal | Validate and deploy the bundle; manage bundle resources and ACLs | Runtime evidence-processing role |
| Source runner service principal | Run dbt and write its short-lived target directory | Evidence Volume or observability base-table access |
| Collector service principal | Enumerate source runs, capture evidence, own facts/views, delete staging | Permission to modify the source job's result or run as the source identity |
| Routine operator group | Query sanitized health | Either Volume or any of the three base tables |

## External prerequisites

These grants exist outside the bundle and must be established by an
administrator.

| Principal | Resource | Minimum access |
|-----------|----------|----------------|
| Deployer | Workspace | Workspace access and permission to create/manage bundle resources |
| Deployer | Runner and collector identities | Service Principal User / permission to set `run_as` |
| Deployer | Parent catalog | `USE CATALOG`, `CREATE SCHEMA`; ability to manage grants on created objects |
| Source runner | Workspace | Workspace access; job-run entitlement required by the workspace |
| Source runner | SQL warehouse | `CAN USE` |
| Source runner | dbt catalog/schema | `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`, `SELECT`, `MODIFY` as required by seed/model builds |
| Collector | Workspace | Workspace access; serverless job-run entitlement required by the workspace |
| Collector | Parent catalog | `USE CATALOG` |
| Collector | `system.lakeflow` tables | `SELECT` when the three optional Lakeflow views are required |

If system-table access is absent, artifact capture and the two guaranteed dbt
views still work; the collector prints `SYSTEM_LAKEFLOW_VIEW_UNAVAILABLE` and
does not refresh the three Lakeflow-backed views.

## Bundle-declared production grants

| Principal | Resource | Grant |
|-----------|----------|-------|
| Deployer | Bundle | `CAN_MANAGE` |
| Collector | Source job | `CAN_VIEW` |
| Collector | Observability schema | `USE_SCHEMA`, `CREATE_TABLE`, `SELECT`, `MODIFY` |
| Runner | Observability schema | `USE_SCHEMA` |
| Collector | Evidence Volume | `READ_VOLUME`, `WRITE_VOLUME` |
| Collector | Staging Volume | `READ_VOLUME`, `WRITE_VOLUME` |
| Runner | Staging Volume | `READ_VOLUME`, `WRITE_VOLUME` |

The runner needs read access because dbt reads its own target directory during
the invocation. The collector's staging write access is used for reconciled
deletion.

## Deployed-file ACLs

The production workflow applies workspace-directory permissions after every
bundle deployment:

| Principal | Permission | Purpose |
|-----------|------------|---------|
| Runner | `CAN_READ` | Read the deployed dbt project |
| Collector | `CAN_RUN` | Execute the deployed collector notebook without edit/manage rights |

These permissions are applied by `.github/workflows/deploy.yml`, not by
`databricks.yml`.

## Operator grants

Routine operators should receive only:

```sql
GRANT USE CATALOG ON CATALOG `<catalog>` TO `<operators>`;
GRANT USE SCHEMA ON SCHEMA `<catalog>`.`<observability-schema>` TO `<operators>`;
GRANT SELECT ON VIEW `<catalog>`.`<observability-schema>`.`dbt_run_health` TO `<operators>`;
GRANT SELECT ON VIEW `<catalog>`.`<observability-schema>`.`dbt_node_health` TO `<operators>`;
```

Grant the three optional views only if they exist and system-table-derived
health is approved. Do not grant operators `READ VOLUME`, `WRITE VOLUME`, or
base-table `SELECT`.

## Inheritance check

Unity Catalog privileges inherit from parent objects. Validate both direct and
inherited grants with `SHOW GRANTS` on the catalog, schema, both Volumes, all
three tables, and every exposed view.

See the official [Unity Catalog privilege model](https://docs.databricks.com/aws/en/data-governance/unity-catalog/manage-privileges/)
and [workspace access control](https://docs.databricks.com/aws/en/security/auth/access-control/).

