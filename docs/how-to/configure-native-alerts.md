---
icon: lucide/bell-ring
---

# Configure native alerts

Configure Databricks job email notifications for source failures, collector
failures, and duration warnings. The repository sends nothing by default:
`notification_emails` is an empty list until you supply approved recipients.

## Before you begin

You need:

- permission to update GitHub repository variables and dispatch the deployment
  workflow;
- authority to approve the protected `prod` environment;
- read-only access to both jobs for verification;
- an internal distribution address approved for operational metadata; and
- the reviewed `main` branch you intend to redeploy.

The M2M deployer—not the human operator—holds job and bundle management
authority.

!!! warning "Treat notification content as operational data"

    Databricks notifications can contain workspace, job, task, and error
    context. Use only an approved internal destination. This project does not
    add a webhook or forward telemetry to another platform.

## Set approved production recipients

Store the JSON array as a non-secret GitHub repository variable:

```bash
gh variable set DATABRICKS_NOTIFICATION_EMAILS \
  --body '["approved-data-operations@example.com"]'
```

The production workflow validates the array and writes its ignored
`.databricks/bundle/prod/variable-overrides.json` file before bundle
validation. It rejects blank, non-string, and overlong entries and falls back
to `[]` when the variable is absent. Complex bundle values cannot be supplied
through `BUNDLE_VAR_*`.

Do not commit a personal address to `databricks.yml`.

## Deploy through the protected identity

Trigger the reviewed `main` workflow and approve the `prod` environment:

```bash
gh workflow run deploy.yml --ref main -f operation=deploy
```

Do not use a human U2M profile to run `bundle deploy --target prod`. The
protected workflow is the production mutation boundary and applies the
recipients together with the reviewed bundle.

The bundle applies the recipients to:

- source-job failure and duration-warning notifications;
- source-task failure on the last retry attempt; and
- collector failure and duration-warning notifications.

The collector deliberately has `max_retries: 0`. A capture problem therefore
remains visible to native notifications; the next scheduled sweep performs the
retry.

## Verify the deployed settings

Resolve each job by exact production name with a read-only U2M profile:

```bash
databricks jobs list \
  --name nyc_taxi_dbt_job \
  --profile bricks-demo \
  --output json
databricks jobs list \
  --name nyc_taxi_dbt_observability_collector \
  --profile bricks-demo \
  --output json
```

Inspect each job:

```console
databricks jobs get <job-id> --profile <profile> --output json
```

Confirm that `settings.email_notifications` contains only approved recipients,
that the source task has `alert_on_last_attempt: true`, and that the collector
still has no in-run retry.

To disable outbound delivery, use the same protected path:

```bash
gh variable set DATABRICKS_NOTIFICATION_EMAILS --body '[]'
gh workflow run deploy.yml --ref main -f operation=deploy
```

Approve `prod`, then repeat the read-only job inspection. Do not remove a
recipient only in the workspace UI; a later bundle deployment would restore the
approved variable value.

## Related reference

- [Bundle configuration](../reference/bundle-config.md)
- [Source job](../reference/source-job.md)
- [Collector job](../reference/collector-job.md)
