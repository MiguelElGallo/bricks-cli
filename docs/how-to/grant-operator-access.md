---
icon: lucide/user-check
---

# Grant operator access

Give an operator read access to sanitized health facts without exposing raw dbt
artifacts, staging, or the three base tables.

## Before you begin

You need permission to grant privileges on the observability catalog, schema,
and views. Decide whether the principal is an approved group or service
principal; prefer a group for human operators.

## Grant the baseline views

Run the following as the owner or a metastore administrator:

```sql
GRANT USE CATALOG ON CATALOG `<catalog>` TO `<operator-principal>`;
GRANT USE SCHEMA ON SCHEMA `<catalog>`.`<observability-schema>`
  TO `<operator-principal>`;

GRANT SELECT ON VIEW
  `<catalog>`.`<observability-schema>`.`dbt_run_health`
  TO `<operator-principal>`;
GRANT SELECT ON VIEW
  `<catalog>`.`<observability-schema>`.`dbt_node_health`
  TO `<operator-principal>`;
```

These two views are always created after the collector initializes the schema.

## Grant optional Lakeflow views

Only if the views exist and their additional timing fields are approved:

```sql
GRANT SELECT ON VIEW
  `<catalog>`.`<observability-schema>`.`lakeflow_job_run_health`
  TO `<operator-principal>`;
GRANT SELECT ON VIEW
  `<catalog>`.`<observability-schema>`.`lakeflow_dbt_task_run_health`
  TO `<operator-principal>`;
GRANT SELECT ON VIEW
  `<catalog>`.`<observability-schema>`.`dbt_job_health`
  TO `<operator-principal>`;
```

Those views are best-effort because their creation requires the collector to
read `system.lakeflow`.

## Verify positive access

Impersonate the operator through your approved access-review process, or ask the
operator to run:

```sql
SELECT *
FROM `<catalog>`.`<observability-schema>`.`dbt_run_health`
LIMIT 1;
```

## Verify negative access

Confirm that the same principal cannot select the restricted tables:

- `dbt_artifact_registry`;
- `dbt_invocations`; and
- `dbt_node_results`.

Also confirm that the principal has neither `READ VOLUME` nor `WRITE VOLUME` on
the staging and evidence Volumes. Do not grant `SELECT ON SCHEMA` or broad
catalog privileges as a shortcut.

Record the grant, its owner, review date, and removal condition in your normal
access-governance system.

## Revoke access

```sql
REVOKE SELECT ON VIEW
  `<catalog>`.`<observability-schema>`.`dbt_run_health`
  FROM `<operator-principal>`;
REVOKE SELECT ON VIEW
  `<catalog>`.`<observability-schema>`.`dbt_node_health`
  FROM `<operator-principal>`;
REVOKE USE SCHEMA ON SCHEMA `<catalog>`.`<observability-schema>`
  FROM `<operator-principal>`;
```

Revoke any optional view grants and remove `USE CATALOG` only when the principal
does not need that catalog for another approved purpose.
