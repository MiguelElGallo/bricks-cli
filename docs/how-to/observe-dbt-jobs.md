---
icon: lucide/activity
---

# Observability operations

Choose the operational result you need. The implementation keeps job status,
artifact evidence, and sanitized health facts inside Databricks. This landing
page routes you to the guide for each task rather than repeating their
contracts.

## Check a healthy deployment

Use [Verify a production deployment](verify-production-deployment.md) after a
merge or identity change. It checks bundle state, workspace directory ACLs,
source and collector run identities, registry evidence, staging cleanup, and
health views.

Use [Query job health](query-job-health.md) for routine checks such as:

- source runs with missing evidence;
- failed or warning dbt nodes;
- quarantined or retryable captures;
- staging cleanup that remains pending; and
- collector backlog within the 59-day discovery window.

## Configure signals and access

- [Configure native alerts](configure-native-alerts.md) for job failure and
  duration warnings. No outbound recipients are configured by default.
- [Grant operator access](grant-operator-access.md) for sanitized views without
  exposing either Volume or the three restricted base tables.

## Investigate a failure

| Signal | First guide |
|---|---|
| Source job failed | [Investigate a source failure](investigate-a-source-failure.md) |
| Collector job failed | [Investigate a collector failure](investigate-a-collector-failure.md) |
| Completed attempt has no artifacts | [Verify missing-artifact capture](verify-failure-capture.md) |
| Unknown state or code | [Capture states](../reference/capture-states.md) and [Error codes](../reference/error-codes.md) |

## Understand the contract

- [Native observability architecture](../explanation/native-observability.md)
- [AttemptKey](../reference/attempt-key.md)
- [Observability objects](../reference/observability-objects.md)
- [Evidence layout](../reference/evidence-layout.md)
- [Evidence lifecycle](../explanation/evidence-lifecycle.md)

The two baseline views, `dbt_run_health` and `dbt_node_health`, do not depend on
system tables. The three `system.lakeflow`-backed views are best-effort; their
absence does not block artifact capture.
