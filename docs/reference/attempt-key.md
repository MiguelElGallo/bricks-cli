---
icon: lucide/fingerprint
---

# AttemptKey

`AttemptKey` is the immutable identity of one concrete source-task attempt. It
prevents logical runs, repairs, retries, and executions from overwriting one
another.

## Signature

```text
AttemptKey(
  workspace_id,
  job_id,
  job_run_id,
  repair_count,
  task_run_id,
  execution_count,
)
```

Defined in `src/observability/collect_dbt_artifacts.py`.

## Fields

| Field | Type | Accepted values | Source |
|-------|------|-----------------|--------|
| `workspace_id` | `BIGINT` | `>= 1` | Authenticated Workspace API / source dynamic value |
| `job_id` | `BIGINT` | `>= 1` | Configured source job / source dynamic value |
| `job_run_id` | `BIGINT` | `>= 1` | Parent source run |
| `repair_count` | `INT` | `>= 0` | Lakeflow repair dynamic value or repair history |
| `task_run_id` | `BIGINT` | `>= 1` | Concrete task run |
| `execution_count` | `INT` | `>= 0` | Lakeflow execution dynamic value; absent-staging discovery derives `attempt_number + 1` |

`task_key` and `upstream_result_state` are recorded attributes, not key fields.

## Uses

All six fields participate in:

- the staging directory;
- the raw and quarantine archive paths;
- the `dbt_artifact_registry` merge key;
- the `dbt_invocations` merge key, with `invocation_id` added; and
- the `dbt_node_results` merge key, with `invocation_id` and `unique_id` added.

## Staging grammar

```text
workspace_id=<workspace_id>/
job_id=<job_id>/
job_run_id=<job_run_id>/
repair_count=<repair_count>/
task_run_id=<task_run_id>/
execution_count=<execution_count>/
target
```

Each numeric directory is parsed strictly. Unknown directory names are ignored,
but a matching key with an invalid value or unsafe filesystem type fails
discovery.

## Retry and repair discovery

For staged attempts, the path labels are producer-controlled after the parent
and task run IDs pass Jobs API correlation. Repair and execution labels are not
independently attested. For an instrumented completed task with no staging leaf,
the collector uses the task's `attempt_number`, anchors it to repair history,
and records:

```text
repair_count   = latest repair anchor whose attempt_number is not newer
execution_count = attempt_number + 1
```

That derived AttemptKey is persisted as terminal `NOT_PRODUCED`. A later sweep
suppresses the same task-run gap.

## Idempotency

An existing terminal key is not recaptured. Retryable states may progress to
another retryable state or to a terminal state. An existing archive hash may
not be replaced by a different digest.

## Example

```text
AttemptKey(123, 456, 789, 0, 790, 1)
```

This identifies execution `1` of task run `790` in original job run `789` for
job `456` in workspace `123`.
