"""Pure helpers for validating and normalizing archived dbt artifacts.

The Databricks notebook adapter lives in ``collect_dbt_artifacts.py``. Keeping
archive handling here makes the security and schema rules testable without a
workspace connection.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import tarfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Final

PARSER_VERSION: Final = "1.0.0"
MANIFEST_SCHEMA: Final = "https://schemas.getdbt.com/dbt/manifest/v12.json"
RUN_RESULTS_SCHEMA: Final = "https://schemas.getdbt.com/dbt/run-results/v6.json"

MAX_ARCHIVE_BYTES: Final = 100 * 1024 * 1024
MAX_MEMBER_BYTES: Final = 50 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES: Final = 250 * 1024 * 1024
MAX_FILE_COUNT: Final = 2_000
MAX_MEMBER_COUNT: Final = 4_000

_REQUIRED_ARTIFACTS: Final = frozenset({"manifest.json", "run_results.json"})
_SAFE_PATH_COMPONENT: Final = re.compile(r"^[A-Za-z0-9_-]+$")
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_SUCCESS_STATUSES: Final = frozenset({"success", "pass", "no-op"})
_WARNING_STATUSES: Final = frozenset({"warn", "partial success"})
_FAILED_STATUSES: Final = frozenset({"error", "fail", "runtime error"})
_SKIPPED_STATUSES: Final = frozenset({"skipped"})
_KNOWN_STATUSES: Final = (
    _SUCCESS_STATUSES | _WARNING_STATUSES | _FAILED_STATUSES | _SKIPPED_STATUSES
)


class ArtifactValidationError(ValueError):
    """A safe, allowlisted artifact validation failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ArchiveScan:
    """Validated archive contents required by the normalizer."""

    selected_files: dict[str, bytes]
    file_count: int
    total_uncompressed_bytes: int


@dataclass(frozen=True)
class NodeResult:
    """Allowlisted dbt node result suitable for a curated Delta table."""

    unique_id: str
    resource_type: str
    node_name: str
    status: str
    execution_seconds: float
    compile_seconds: float | None
    execute_seconds: float | None
    failures: int | None
    rows_affected: int | None


@dataclass(frozen=True)
class ParsedArtifacts:
    """Allowlisted invocation and node facts from one dbt invocation."""

    invocation_id: str
    generated_at: datetime
    dbt_version: str
    adapter_type: str
    command: str
    elapsed_seconds: float
    invocation_status: str
    total_nodes: int
    success_nodes: int
    warning_nodes: int
    failed_nodes: int
    skipped_nodes: int
    manifest_sha256: str
    manifest_schema_version: str
    run_results_schema_version: str
    nodes: tuple[NodeResult, ...]


def archive_sha256(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for an archive."""

    return hashlib.sha256(data).hexdigest()


def scan_archive(data: bytes) -> ArchiveScan:
    """Inspect a tar archive without extracting files to the filesystem."""

    if not data or len(data) > MAX_ARCHIVE_BYTES:
        raise ArtifactValidationError("ARCHIVE_SIZE_INVALID")

    selected: dict[str, bytes] = {}
    file_count = 0
    member_count = 0
    total_size = 0

    try:
        with tarfile.open(fileobj=BytesIO(data), mode="r:*") as archive:
            for member in archive:
                member_count += 1
                if member_count > MAX_MEMBER_COUNT:
                    raise ArtifactValidationError("ARCHIVE_MEMBER_COUNT_EXCEEDED")
                _validate_member_name(member.name)
                if not member.isfile():
                    continue

                file_count += 1
                if file_count > MAX_FILE_COUNT:
                    raise ArtifactValidationError("ARCHIVE_FILE_COUNT_EXCEEDED")
                if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                    raise ArtifactValidationError("ARCHIVE_MEMBER_SIZE_EXCEEDED")

                total_size += member.size
                if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise ArtifactValidationError("ARCHIVE_EXPANDED_SIZE_EXCEEDED")

                basename = PurePosixPath(member.name).name
                if basename not in _REQUIRED_ARTIFACTS:
                    continue
                if basename in selected:
                    raise ArtifactValidationError("DUPLICATE_REQUIRED_ARTIFACT")

                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ArtifactValidationError("ARCHIVE_MEMBER_UNREADABLE")
                payload = extracted.read(MAX_MEMBER_BYTES + 1)
                if len(payload) > MAX_MEMBER_BYTES:
                    raise ArtifactValidationError("ARCHIVE_MEMBER_SIZE_EXCEEDED")
                if len(payload) != member.size:
                    raise ArtifactValidationError("ARCHIVE_MEMBER_UNREADABLE")
                selected[basename] = payload
    except ArtifactValidationError:
        raise
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise ArtifactValidationError("ARCHIVE_FORMAT_INVALID") from exc

    missing = _REQUIRED_ARTIFACTS.difference(selected)
    if missing:
        raise ArtifactValidationError("MISSING_REQUIRED_ARTIFACT")

    return ArchiveScan(
        selected_files=selected,
        file_count=file_count,
        total_uncompressed_bytes=total_size,
    )


def parse_artifacts(scan: ArchiveScan) -> ParsedArtifacts:
    """Normalize one supported manifest and run-results pair."""

    manifest = _load_json(scan.selected_files["manifest.json"])
    run_results = _load_json(scan.selected_files["run_results.json"])
    manifest_metadata = _metadata(manifest)
    result_metadata = _metadata(run_results)

    manifest_schema = _required_text(manifest_metadata, "dbt_schema_version", 200)
    result_schema = _required_text(result_metadata, "dbt_schema_version", 200)
    if manifest_schema != MANIFEST_SCHEMA or result_schema != RUN_RESULTS_SCHEMA:
        raise ArtifactValidationError("UNSUPPORTED_ARTIFACT_SCHEMA")

    manifest_invocation = _required_text(manifest_metadata, "invocation_id", 128)
    result_invocation = _required_text(result_metadata, "invocation_id", 128)
    if manifest_invocation != result_invocation:
        raise ArtifactValidationError("INVOCATION_ID_MISMATCH")

    definitions = manifest.get("nodes")
    raw_results = run_results.get("results")
    if not isinstance(definitions, dict) or not isinstance(raw_results, list):
        raise ArtifactValidationError("ARTIFACT_STRUCTURE_INVALID")

    nodes: list[NodeResult] = []
    seen_ids: set[str] = set()
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            raise ArtifactValidationError("ARTIFACT_STRUCTURE_INVALID")
        unique_id = _required_text(raw_result, "unique_id", 1_024)
        if unique_id in seen_ids:
            raise ArtifactValidationError("DUPLICATE_NODE_RESULT")
        seen_ids.add(unique_id)

        definition = definitions.get(unique_id, {})
        if not isinstance(definition, dict):
            definition = {}
        status = _required_text(raw_result, "status", 64).lower()
        if status not in _KNOWN_STATUSES:
            raise ArtifactValidationError("UNSUPPORTED_NODE_STATUS")
        nodes.append(
            NodeResult(
                unique_id=unique_id,
                resource_type=_safe_text(definition.get("resource_type"), "unknown", 64),
                node_name=_safe_text(definition.get("name"), unique_id, 512),
                status=status,
                execution_seconds=_safe_nonnegative_float(
                    raw_result.get("execution_time"), default=0.0
                ),
                compile_seconds=_timing_seconds(raw_result.get("timing"), "compile"),
                execute_seconds=_timing_seconds(raw_result.get("timing"), "execute"),
                failures=_optional_int(raw_result.get("failures")),
                rows_affected=_rows_affected(raw_result.get("adapter_response")),
            )
        )

    counts = Counter(node.status for node in nodes)
    success_nodes = sum(counts[status] for status in _SUCCESS_STATUSES)
    failed_nodes = sum(counts[status] for status in _FAILED_STATUSES)
    warning_nodes = sum(counts[status] for status in _WARNING_STATUSES)
    skipped_nodes = sum(counts[status] for status in _SKIPPED_STATUSES)
    invocation_status = "failed" if failed_nodes else "warning" if warning_nodes else "success"

    args = run_results.get("args")
    command = "unknown"
    if isinstance(args, dict):
        candidate = _safe_text(args.get("which"), "unknown", 64).lower()
        if candidate in {"build", "run", "seed", "test", "snapshot", "source"}:
            command = candidate

    return ParsedArtifacts(
        invocation_id=result_invocation,
        generated_at=_parse_timestamp(_required_text(result_metadata, "generated_at", 64)),
        dbt_version=_required_text(result_metadata, "dbt_version", 64),
        adapter_type=_safe_text(manifest_metadata.get("adapter_type"), "unknown", 64),
        command=command,
        elapsed_seconds=_safe_nonnegative_float(run_results.get("elapsed_time"), default=0.0),
        invocation_status=invocation_status,
        total_nodes=len(nodes),
        success_nodes=success_nodes,
        warning_nodes=warning_nodes,
        failed_nodes=failed_nodes,
        skipped_nodes=skipped_nodes,
        manifest_sha256=hashlib.sha256(scan.selected_files["manifest.json"]).hexdigest(),
        manifest_schema_version=manifest_schema,
        run_results_schema_version=result_schema,
        nodes=tuple(nodes),
    )


def build_archive_path(
    *,
    catalog: str,
    schema: str,
    volume: str,
    workspace_id: int,
    job_id: int,
    job_run_id: int,
    repair_count: int,
    task_run_id: int,
    execution_count: int,
    digest: str,
    quarantined: bool,
) -> str:
    """Build a content-addressed UC Volume path from allowlisted components."""

    for component in (catalog, schema, volume):
        if not _SAFE_PATH_COMPONENT.fullmatch(component):
            raise ArtifactValidationError("STORAGE_IDENTIFIER_INVALID")
    if min(workspace_id, job_id, job_run_id, task_run_id) < 1:
        raise ArtifactValidationError("RUN_IDENTIFIER_INVALID")
    if min(repair_count, execution_count) < 0:
        raise ArtifactValidationError("RUN_IDENTIFIER_INVALID")
    if not _SHA256.fullmatch(digest):
        raise ArtifactValidationError("ARCHIVE_HASH_INVALID")

    zone = "quarantine" if quarantined else "raw"
    return (
        f"/Volumes/{catalog}/{schema}/{volume}/{zone}/"
        f"workspace_id={workspace_id}/job_id={job_id}/job_run_id={job_run_id}/"
        f"repair_count={repair_count}/task_run_id={task_run_id}/"
        f"execution_count={execution_count}/sha256={digest}/dbt-output.tar.gz"
    )


def check_existing_hash(existing: str | None, current: str) -> None:
    """Reject a different archive for an already registered task run."""

    if existing and existing != current:
        raise ArtifactValidationError("ARCHIVE_HASH_COLLISION")


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or any(ord(character) < 32 for character in name)
    ):
        raise ArtifactValidationError("ARCHIVE_PATH_INVALID")


def _load_json(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ArtifactValidationError("ARTIFACT_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise ArtifactValidationError("ARTIFACT_STRUCTURE_INVALID")
    return value


def _metadata(document: dict[str, Any]) -> dict[str, Any]:
    value = document.get("metadata")
    if not isinstance(value, dict):
        raise ArtifactValidationError("ARTIFACT_METADATA_MISSING")
    return value


def _required_text(mapping: dict[str, Any], key: str, max_length: int) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ArtifactValidationError("ARTIFACT_FIELD_INVALID")
    return value


def _safe_text(value: Any, default: str, max_length: int) -> str:
    if not isinstance(value, str) or not value:
        return default[:max_length]
    return value[:max_length]


def _safe_nonnegative_float(value: Any, *, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    converted = float(value)
    return converted if math.isfinite(converted) and converted >= 0 else default


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _rows_affected(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    return _optional_int(value.get("rows_affected"))


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtifactValidationError("ARTIFACT_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _timing_seconds(value: Any, timing_name: str) -> float | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict) or item.get("name") != timing_name:
            continue
        started = item.get("started_at")
        completed = item.get("completed_at")
        if not isinstance(started, str) or not isinstance(completed, str):
            return None
        seconds = (_parse_timestamp(completed) - _parse_timestamp(started)).total_seconds()
        return max(seconds, 0.0)
    return None
