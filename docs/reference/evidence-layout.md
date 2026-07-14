---
icon: lucide/database-backup
---

# Evidence layout

The source writes short-lived dbt output to one managed Volume. The collector
writes deterministic, content-addressed evidence to a separate managed Volume.

## Staging path

```text
/Volumes/<catalog>/<observability-schema>/<staging-volume>/
  workspace_id=<workspace-id>/
  job_id=<job-id>/
  job_run_id=<job-run-id>/
  repair_count=<repair-count>/
  task_run_id=<task-run-id>/
  execution_count=<execution-count>/
  target/
    manifest.json
    run_results.json
```

The source may create other dbt target output, but the collector reads only the
two named JSON files. It rejects symlinks, path escape, non-regular files, and
content that changes during reading.

## Canonical archive path

```text
/Volumes/<catalog>/<observability-schema>/<evidence-volume>/raw/
  workspace_id=<workspace-id>/job_id=<job-id>/job_run_id=<job-run-id>/
  repair_count=<repair-count>/task_run_id=<task-run-id>/
  execution_count=<execution-count>/sha256=<64-lowercase-hex>/
  dbt-output.tar.gz
```

Valid archives contain exactly:

```text
target/manifest.json
target/run_results.json
```

## Quarantine path

Invalid staged content that can be packaged durably uses the same grammar below
`quarantine/` instead of `raw/`. A quarantine archive may contain only one of
the required files when the other was missing; the validation code records why
the pair was rejected.

## Deterministic encoding

The collector creates gzip-compressed PAX tar data with:

| Property | Value |
|----------|-------|
| Member order | `manifest.json`, then `run_results.json` when present |
| Member path | `target/<name>` |
| Mode | `0600` |
| Modification time | `0` |
| UID/GID | `0` / `0` |
| User/group name | empty |
| Gzip modification time | `0` |

The SHA-256 is calculated from the complete compressed archive bytes. Writes
use create-only mode; an existing object is accepted only when its remote hash
matches. A different digest for an already registered AttemptKey is rejected.

## Size and traversal limits

| Limit | Value | Error |
|-------|-------|-------|
| Staged file read | 100 MiB per file | `STAGED_ARTIFACT_SIZE_INVALID` |
| Total selected staged payload | 100 MiB | `STAGED_ARTIFACT_SIZE_INVALID` |
| Compressed archive | 100 MiB | `ARCHIVE_SIZE_INVALID` |
| Remote archive verification | 100 MiB | `ARCHIVE_REMOTE_SIZE_INVALID` |
| Tar file member | 50 MiB | `ARCHIVE_MEMBER_SIZE_EXCEEDED` |
| Total uncompressed tar files | 250 MiB | `ARCHIVE_EXPANDED_SIZE_EXCEEDED` |
| File members scanned | 2,000 | `ARCHIVE_FILE_COUNT_EXCEEDED` |
| All tar members scanned | 4,000 | `ARCHIVE_MEMBER_COUNT_EXCEEDED` |
| Entries scanned in one staging directory | 10,000 | `STAGING_DIRECTORY_LIMIT_EXCEEDED` |
| Entries deleted in one attempt tree | 10,000 | `STAGING_CLEANUP_ENTRY_LIMIT_EXCEEDED` |
| Cleanup recursion depth | 16 | `STAGING_CLEANUP_DEPTH_EXCEEDED` |

MiB values use `1024 × 1024` bytes.

## Format contract

| Item | Accepted value |
|------|----------------|
| Storage identifiers | `[A-Za-z0-9_-]+` |
| SHA-256 path component | 64 lowercase hexadecimal characters |
| Manifest schema | `https://schemas.getdbt.com/dbt/manifest/v12.json` |
| Run-results schema | `https://schemas.getdbt.com/dbt/run-results/v6.json` |
| Parser version | `1.0.0` |

## Retention and integrity boundary

Production marks the observability schema and both Volumes
`lifecycle.prevent_destroy: true`. The collector never overwrites a canonical
object and verifies its digest, which makes unexpected change detectable at the
application layer.

!!! warning "Managed Volume is not WORM"
    A sufficiently privileged Databricks identity can still mutate or delete a
    managed Volume object. Write-once regulatory retention requires a separate
    approved control. See the official [Unity Catalog Volumes documentation](https://docs.databricks.com/aws/en/volumes/).

