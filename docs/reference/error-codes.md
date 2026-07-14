---
icon: lucide/circle-alert
---

# Error codes

Registry fields and bounded collector summaries expose stable uppercase codes
instead of raw artifact content. Spark, Delta, or platform failures outside the
per-attempt handling boundary can still surface native exceptions in the
restricted collector job log.

## State mapping

| Failure phase | Registry/result behavior |
|---------------|--------------------------|
| No staged content | `NOT_PRODUCED`, terminal; current sweep fails |
| Staging read before durable archive | `RETRYABLE_ERROR`; later sweep retries |
| Archive upload/integrity persistence | `UPLOAD_FAILED`; later sweep retries |
| Packaged content validation | Archive retained under `quarantine/`; `QUARANTINED`, terminal; current sweep fails |
| Discovery/configuration before an AttemptKey can be trusted | Sweep fails; code is normally job output, not a new registry row |
| Staging deletion after terminal capture | Capture stays terminal; cleanup remains `PENDING` with its code |

## Runtime, identity, and discovery

| Code | Meaning |
|------|---------|
| `RUNTIME_PARAMETER_INVALID` | Widget value is empty, out of bounds, too long, contains a control character, or otherwise violates its contract |
| `RUN_IDENTIFIER_INVALID` | Required run identifier is non-numeric, below its minimum, or inconsistent with path construction |
| `RUN_SOURCE_MISMATCH` | Jobs API returned a run for a different job than configured |
| `RUN_LIST_API_ERROR` | Completed-run enumeration failed |
| `RUN_DETAIL_API_ERROR` | Detailed run/history lookup failed while correlating staging |
| `STORAGE_IDENTIFIER_INVALID` | Catalog, schema, Volume, or other storage identifier does not match `[A-Za-z0-9_-]+` |
| `STAGING_LIST_ERROR` | A staging directory could not be scanned |
| `STAGING_DIRECTORY_LIMIT_EXCEEDED` | More than 10,000 entries were encountered in one scanned directory |
| `STAGING_DIRECTORY_TYPE_INVALID` | A staging identity directory is a symlink or not a real directory |
| `STAGING_TASK_RUN_UNCORRELATED` | Staging names a task run that cannot be authorized from source run/history data |
| `DUPLICATE_ATTEMPT_STAGING` | The same full AttemptKey was discovered more than once |

These codes normally fail discovery before the collector selects a capture
batch. Existing evidence remains unchanged.

## Staged artifact reads

| Code | Meaning | Usual capture state |
|------|---------|---------------------|
| `STAGED_ARTIFACT_NOT_PRODUCED` | Attempt/target path is absent or neither required JSON file exists | `NOT_PRODUCED` |
| `STAGED_ARTIFACT_MISSING` | A read marked required found no file; defensive contract | `RETRYABLE_ERROR` |
| `STAGED_ARTIFACT_READ_ERROR` | POSIX read failed for a reason other than absence | `RETRYABLE_ERROR` |
| `STAGED_ARTIFACT_SIZE_INVALID` | A staged file or selected pair exceeds 100 MiB | `RETRYABLE_ERROR` |
| `STAGED_ARTIFACT_TYPE_INVALID` | Attempt, target, or file path is a symlink or has an unexpected filesystem type | `RETRYABLE_ERROR` |
| `STAGED_ARTIFACT_CHANGED_DURING_READ` | Device/inode, size, or modification time changed across the read | `RETRYABLE_ERROR` |

## Archive structure and limits

These codes are normally terminal `QUARANTINED` when staged bytes were packaged
and retained. `ARCHIVE_SIZE_INVALID` can instead be retryable when deterministic
archive construction itself exceeds the limit.

| Code | Meaning |
|------|---------|
| `ARCHIVE_SIZE_INVALID` | Archive is empty or exceeds 100 MiB |
| `ARCHIVE_FORMAT_INVALID` | Bytes are not a readable supported tar stream |
| `ARCHIVE_PATH_INVALID` | Member path is empty, absolute, traverses with `..`, contains backslashes, or has control characters |
| `ARCHIVE_MEMBER_COUNT_EXCEEDED` | More than 4,000 tar members were scanned |
| `ARCHIVE_FILE_COUNT_EXCEEDED` | More than 2,000 regular-file members were scanned |
| `ARCHIVE_MEMBER_SIZE_EXCEEDED` | A regular-file member exceeds 50 MiB or yields more bytes than allowed |
| `ARCHIVE_EXPANDED_SIZE_EXCEEDED` | Sum of regular-file sizes exceeds 250 MiB |
| `ARCHIVE_MEMBER_UNREADABLE` | A declared file member cannot be read completely |
| `DUPLICATE_REQUIRED_ARTIFACT` | More than one member has basename `manifest.json` or `run_results.json` |
| `MISSING_REQUIRED_ARTIFACT` | One or both required artifact basenames are absent |

## Artifact parsing

These codes produce terminal `QUARANTINED` after the rejected bytes are stored.

| Code | Meaning |
|------|---------|
| `ARTIFACT_JSON_INVALID` | Required artifact is not valid UTF-8 JSON object content |
| `ARTIFACT_STRUCTURE_INVALID` | Required top-level object/list structure is absent or wrong |
| `ARTIFACT_METADATA_MISSING` | Required `metadata` object is absent |
| `ARTIFACT_FIELD_INVALID` | Required string is absent, empty, wrong type, or longer than its allowlist bound |
| `ARTIFACT_TIMESTAMP_INVALID` | Required timestamp cannot be parsed as ISO format |
| `UNSUPPORTED_ARTIFACT_SCHEMA` | Manifest is not v12 or run-results is not v6 |
| `INVOCATION_ID_MISMATCH` | Manifest and run-results invocation IDs differ |
| `DUPLICATE_NODE_RESULT` | Run-results repeats a dbt `unique_id` |
| `UNSUPPORTED_NODE_STATUS` | Node status is outside the accepted status set |

## Content-addressed persistence

| Code | Meaning | Usual capture state |
|------|---------|---------------------|
| `ARCHIVE_HASH_INVALID` | Digest is not 64 lowercase hexadecimal characters | Sweep failure; defensive invariant |
| `ARCHIVE_HASH_COLLISION` | Existing registry/object digest differs for the same identity/path | `UPLOAD_FAILED` when detected during upload; otherwise existing state is preserved |
| `ARCHIVE_UPLOAD_ERROR` | Evidence directory or file could not be created/written safely | `UPLOAD_FAILED` |
| `ARCHIVE_UPLOAD_INCOMPLETE` | A write returned no forward progress | `UPLOAD_FAILED` |
| `ARCHIVE_REMOTE_READ_ERROR` | Persisted object could not be read for hash verification | `UPLOAD_FAILED` |
| `ARCHIVE_REMOTE_SIZE_INVALID` | Persisted object exceeds 100 MiB during verification | `UPLOAD_FAILED` |

## Registry and cleanup

| Code | Meaning | Effect |
|------|---------|--------|
| `DUPLICATE_REGISTRY_KEY` | More than one registry row exists for one AttemptKey | Sweep fails; manual data repair required |
| `STAGING_CLEANUP_TYPE_INVALID` | Cleanup encountered a symlink, unexpected type, or path outside the attempt root | Capture remains terminal; cleanup `PENDING` |
| `STAGING_CLEANUP_DEPTH_EXCEEDED` | Cleanup recursion passed depth 16 | Capture remains terminal; cleanup `PENDING` |
| `STAGING_CLEANUP_ENTRY_LIMIT_EXCEEDED` | Cleanup visited more than 10,000 entries | Capture remains terminal; cleanup `PENDING` |
| `STAGING_CLEANUP_ERROR` | Filesystem deletion failed | Capture remains terminal; cleanup `PENDING` |
| `STAGING_CLEANUP_STATE_INVALID` | Cleanup status/error combination or persisted registry state violates the contract | Sweep fails; registry requires inspection |
| `STAGING_CLEANUP_STATE_ERROR` | Unexpected exception prevented cleanup-state persistence | Sweep output signal; inspect registry before rerun |

## Non-registry signals

| Signal | Meaning |
|--------|---------|
| `UNEXPECTED_CAPTURE_ERROR` | Non-allowlisted exception escaped one attempt; raw exception is not exposed by the collector summary |
| `SYSTEM_LAKEFLOW_VIEW_UNAVAILABLE` | Optional system-table views were not fully refreshed; artifact capture and guaranteed dbt views continue |
| `BATCH_DEFERRED` | More discovered attempt work remained than the bounded capture budget; a later sweep continues it |

## Example query

```sql
SELECT
  capture_status,
  capture_error_code,
  staging_cleanup_status,
  staging_cleanup_error_code,
  count(*) AS attempts
FROM `<catalog>`.`<observability-schema>`.`dbt_artifact_registry`
GROUP BY ALL
ORDER BY attempts DESC;
```
