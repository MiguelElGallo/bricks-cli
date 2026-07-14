# Databricks notebook source
"""Build governed evidence archives from completed dbt Core task artifacts."""

from __future__ import annotations

import gzip
import hashlib
import importlib
import os
import re
import stat
import tarfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

try:
    from collector_core import (
        MAX_ARCHIVE_BYTES,
        PARSER_VERSION,
        ArchiveScan,
        ArtifactValidationError,
        ParsedArtifacts,
        archive_sha256,
        build_archive_path,
        check_existing_hash,
        parse_artifacts,
        scan_archive,
    )
except ModuleNotFoundError:
    # Local tests import this file as a package; deployed notebooks resolve the
    # sibling workspace file directly from the notebook directory.
    from observability.collector_core import (
        MAX_ARCHIVE_BYTES,
        PARSER_VERSION,
        ArchiveScan,
        ArtifactValidationError,
        ParsedArtifacts,
        archive_sha256,
        build_archive_path,
        check_existing_hash,
        parse_artifacts,
        scan_archive,
    )
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,128}$")
_MAX_STAGING_ENTRIES = 10_000
_MAX_STAGING_DEPTH = 16

_REGISTRY_SCHEMA = """
workspace_id LONG, job_id LONG, job_run_id LONG, repair_count INT,
task_run_id LONG, execution_count INT,
task_key STRING, upstream_result_state STRING, capture_status STRING,
capture_error_code STRING, captured_at TIMESTAMP,
staging_cleanup_status STRING, staging_cleanup_error_code STRING,
staging_cleanup_updated_at TIMESTAMP, staging_deleted_at TIMESTAMP,
archive_path STRING, archive_sha256 STRING, archive_bytes LONG, file_count INT,
total_uncompressed_bytes LONG, invocation_id STRING, dbt_version STRING,
adapter_type STRING, manifest_schema_version STRING,
run_results_schema_version STRING, parser_version STRING
"""

_INVOCATION_SCHEMA = """
workspace_id LONG, job_id LONG, job_run_id LONG, repair_count INT,
task_run_id LONG, execution_count INT,
invocation_id STRING, generated_at TIMESTAMP, dbt_version STRING,
adapter_type STRING, command STRING, invocation_status STRING,
elapsed_seconds DOUBLE, total_nodes INT, success_nodes INT, warning_nodes INT,
failed_nodes INT, skipped_nodes INT, manifest_sha256 STRING,
parser_version STRING, ingested_at TIMESTAMP
"""

_NODE_SCHEMA = """
workspace_id LONG, job_id LONG, job_run_id LONG, repair_count INT,
task_run_id LONG, execution_count INT,
invocation_id STRING, unique_id STRING, resource_type STRING, node_name STRING,
status STRING, execution_seconds DOUBLE, compile_seconds DOUBLE,
execute_seconds DOUBLE, failures LONG, rows_affected LONG, ingested_at TIMESTAMP
"""


@dataclass(frozen=True)
class AttemptKey:
    workspace_id: int
    job_id: int
    job_run_id: int
    repair_count: int
    task_run_id: int
    execution_count: int


@dataclass(frozen=True)
class CaptureContext:
    """Identifiers for one completed source dbt task attempt."""

    workspace_id: int
    job_id: int
    job_run_id: int
    task_run_id: int
    repair_count: int
    execution_count: int
    task_key: str
    upstream_result_state: str
    catalog: str
    schema: str
    volume: str
    staging_volume: str

    @property
    def attempt_key(self) -> AttemptKey:
        return AttemptKey(
            workspace_id=self.workspace_id,
            job_id=self.job_id,
            job_run_id=self.job_run_id,
            repair_count=self.repair_count,
            task_run_id=self.task_run_id,
            execution_count=self.execution_count,
        )


@dataclass(frozen=True)
class DiscoveryGap:
    """An instrumented terminal task with no discoverable attempt directory."""

    job_run_id: int
    task_run_id: int


@dataclass(frozen=True)
class CaptureDiscovery:
    """Staged attempts and independent gaps found from completed source runs."""

    contexts: tuple[CaptureContext, ...]
    gaps: tuple[DiscoveryGap, ...]


@dataclass(frozen=True)
class RegistryCaptureState:
    """Durable capture and cleanup state for every registered attempt."""

    terminal_attempts: frozenset[AttemptKey]
    last_attempted_at: dict[AttemptKey, float]
    cleanup_pending: tuple[CaptureContext, ...]


@dataclass(frozen=True)
class CollectorConfig:
    """Allowlisted parameters for the post-run collector job."""

    workspace_id: int
    source_job_id: int
    source_task_key: str
    lookback_days: int
    max_task_runs_per_sweep: int
    catalog: str
    schema: str
    volume: str
    staging_volume: str

    @classmethod
    def from_widgets(cls, *, workspace_id: int) -> CollectorConfig:
        return cls(
            workspace_id=workspace_id,
            source_job_id=_integer_widget("source_job_id"),
            source_task_key=_identifier_widget("source_task_key"),
            lookback_days=_bounded_integer_widget("lookback_days", minimum=1, maximum=59),
            max_task_runs_per_sweep=_bounded_integer_widget(
                "max_task_runs_per_sweep", minimum=1, maximum=100
            ),
            catalog=_identifier_widget("observability_catalog"),
            schema=_identifier_widget("observability_schema"),
            volume=_identifier_widget("observability_volume"),
            staging_volume=_identifier_widget("observability_staging_volume"),
        )


def _widget(name: str) -> str:
    runtime = importlib.import_module("databricks.sdk.runtime")
    return str(runtime.dbutils.widgets.get(name))


def _integer_widget(name: str) -> int:
    value = _widget(name)
    if not value.isdigit():
        raise ArtifactValidationError("RUN_IDENTIFIER_INVALID")
    return int(value)


def _bounded_integer_widget(name: str, *, minimum: int, maximum: int) -> int:
    value = _integer_widget(name)
    if not minimum <= value <= maximum:
        raise ArtifactValidationError("RUNTIME_PARAMETER_INVALID")
    return value


def _safe_widget(name: str) -> str:
    value = _widget(name)
    if not value or len(value) > 128 or any(ord(character) < 32 for character in value):
        raise ArtifactValidationError("RUNTIME_PARAMETER_INVALID")
    return value


def _identifier_widget(name: str) -> str:
    value = _safe_widget(name)
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ArtifactValidationError("STORAGE_IDENTIFIER_INVALID")
    return value


def _spark_session() -> Any:
    pyspark_sql = importlib.import_module("pyspark.sql")
    return pyspark_sql.SparkSession.builder.getOrCreate()


def _quoted(value: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ArtifactValidationError("STORAGE_IDENTIFIER_INVALID")
    return f"`{value}`"


def _object_name(context: CaptureContext | CollectorConfig, object_name: str) -> str:
    return ".".join((_quoted(context.catalog), _quoted(context.schema), _quoted(object_name)))


def _staging_root(context: CaptureContext) -> str:
    for component in (context.catalog, context.schema, context.staging_volume):
        if not _SAFE_IDENTIFIER.fullmatch(component):
            raise ArtifactValidationError("STORAGE_IDENTIFIER_INVALID")
    if (
        min(
            context.workspace_id,
            context.job_id,
            context.job_run_id,
            context.task_run_id,
        )
        < 1
        or min(context.repair_count, context.execution_count) < 0
    ):
        raise ArtifactValidationError("RUN_IDENTIFIER_INVALID")
    return (
        f"/Volumes/{context.catalog}/{context.schema}/{context.staging_volume}/"
        f"workspace_id={context.workspace_id}/job_id={context.job_id}/"
        f"job_run_id={context.job_run_id}/repair_count={context.repair_count}/"
        f"task_run_id={context.task_run_id}/execution_count={context.execution_count}"
    )


def _validate_staging_path(
    path: str,
    *,
    final_directory: bool,
    invalid_code: str,
) -> os.stat_result:
    """Reject symlinks and non-POSIX types in producer-writable staging paths."""

    if os.path.normpath(path) != path or not os.path.isabs(path):
        raise ArtifactValidationError(invalid_code)

    paths = [path]
    if path.startswith("/Volumes/"):
        components = path.split("/")
        if len(components) < 5:
            raise ArtifactValidationError(invalid_code)
        volume_root = "/".join(components[:5])
        paths = [volume_root]
        current_path = volume_root
        for component in components[5:]:
            current_path = os.path.join(current_path, component)
            paths.append(current_path)
        try:
            if os.path.commonpath(
                (os.path.realpath(volume_root), os.path.realpath(path))
            ) != os.path.realpath(volume_root):
                raise ArtifactValidationError(invalid_code)
        except ValueError:
            raise ArtifactValidationError(invalid_code) from None

    final_metadata: os.stat_result | None = None
    for index, component_path in enumerate(paths):
        metadata = os.lstat(component_path)
        is_final = index == len(paths) - 1
        expected_directory = not is_final or final_directory
        if stat.S_ISLNK(metadata.st_mode):
            raise ArtifactValidationError(invalid_code)
        if expected_directory and not stat.S_ISDIR(metadata.st_mode):
            raise ArtifactValidationError(invalid_code)
        if not expected_directory and not stat.S_ISREG(metadata.st_mode):
            raise ArtifactValidationError(invalid_code)
        final_metadata = metadata

    if final_metadata is None:
        raise ArtifactValidationError(invalid_code)
    return final_metadata


def _ensure_delta_objects(spark: Any, context: CaptureContext | CollectorConfig) -> None:
    registry = _object_name(context, "dbt_artifact_registry")
    invocations = _object_name(context, "dbt_invocations")
    nodes = _object_name(context, "dbt_node_results")

    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {registry} (
          workspace_id BIGINT NOT NULL,
          job_id BIGINT NOT NULL,
          job_run_id BIGINT NOT NULL,
          repair_count INT NOT NULL,
          task_run_id BIGINT NOT NULL,
          execution_count INT NOT NULL,
          task_key STRING NOT NULL,
          upstream_result_state STRING NOT NULL,
          capture_status STRING NOT NULL,
          capture_error_code STRING,
          captured_at TIMESTAMP NOT NULL,
          staging_cleanup_status STRING NOT NULL,
          staging_cleanup_error_code STRING,
          staging_cleanup_updated_at TIMESTAMP NOT NULL,
          staging_deleted_at TIMESTAMP,
          archive_path STRING,
          archive_sha256 STRING,
          archive_bytes BIGINT,
          file_count INT,
          total_uncompressed_bytes BIGINT,
          invocation_id STRING,
          dbt_version STRING,
          adapter_type STRING,
          manifest_schema_version STRING,
          run_results_schema_version STRING,
          parser_version STRING NOT NULL
        ) USING DELTA
        COMMENT 'Restricted registry of content-addressed canonical dbt evidence archives'
        TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
        """
    )
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {invocations} (
          workspace_id BIGINT NOT NULL,
          job_id BIGINT NOT NULL,
          job_run_id BIGINT NOT NULL,
          repair_count INT NOT NULL,
          task_run_id BIGINT NOT NULL,
          execution_count INT NOT NULL,
          invocation_id STRING NOT NULL,
          generated_at TIMESTAMP NOT NULL,
          dbt_version STRING NOT NULL,
          adapter_type STRING NOT NULL,
          command STRING NOT NULL,
          invocation_status STRING NOT NULL,
          elapsed_seconds DOUBLE NOT NULL,
          total_nodes INT NOT NULL,
          success_nodes INT NOT NULL,
          warning_nodes INT NOT NULL,
          failed_nodes INT NOT NULL,
          skipped_nodes INT NOT NULL,
          manifest_sha256 STRING NOT NULL,
          parser_version STRING NOT NULL,
          ingested_at TIMESTAMP NOT NULL
        ) USING DELTA
        COMMENT 'Sanitized dbt invocation-level operational facts'
        TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
        """
    )
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {nodes} (
          workspace_id BIGINT NOT NULL,
          job_id BIGINT NOT NULL,
          job_run_id BIGINT NOT NULL,
          repair_count INT NOT NULL,
          task_run_id BIGINT NOT NULL,
          execution_count INT NOT NULL,
          invocation_id STRING NOT NULL,
          unique_id STRING NOT NULL,
          resource_type STRING NOT NULL,
          node_name STRING NOT NULL,
          status STRING NOT NULL,
          execution_seconds DOUBLE NOT NULL,
          compile_seconds DOUBLE,
          execute_seconds DOUBLE,
          failures BIGINT,
          rows_affected BIGINT,
          ingested_at TIMESTAMP NOT NULL
        ) USING DELTA
        COMMENT 'Sanitized dbt model, seed, and test execution facts'
        TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
        """
    )


def _create_curated_views(spark: Any, context: CaptureContext | CollectorConfig) -> None:
    registry = _object_name(context, "dbt_artifact_registry")
    invocations = _object_name(context, "dbt_invocations")
    nodes = _object_name(context, "dbt_node_results")
    run_view = _object_name(context, "dbt_run_health")
    node_view = _object_name(context, "dbt_node_health")
    lakeflow_view = _object_name(context, "lakeflow_job_run_health")
    lakeflow_task_view = _object_name(context, "lakeflow_dbt_task_run_health")
    combined_view = _object_name(context, "dbt_job_health")

    spark.sql(
        f"""
        CREATE OR REPLACE VIEW {run_view}
        COMMENT 'Sanitized dbt invocation health; raw logs and SQL are excluded'
        AS SELECT
          r.workspace_id,
          r.job_id,
          r.job_run_id,
          r.repair_count,
          r.task_run_id,
          r.execution_count,
          r.task_key,
          r.upstream_result_state,
          r.capture_status,
          r.capture_error_code,
          r.captured_at,
          r.staging_cleanup_status,
          r.staging_cleanup_error_code,
          r.staging_cleanup_updated_at,
          r.staging_deleted_at,
          r.archive_sha256,
          i.invocation_id,
          i.generated_at,
          i.dbt_version,
          i.adapter_type,
          i.command,
          i.invocation_status,
          i.elapsed_seconds,
          i.total_nodes,
          i.success_nodes,
          i.warning_nodes,
          i.failed_nodes,
          i.skipped_nodes
        FROM {registry} AS r
        LEFT JOIN {invocations} AS i
          ON r.workspace_id = i.workspace_id
         AND r.job_id = i.job_id
         AND r.job_run_id = i.job_run_id
         AND r.repair_count = i.repair_count
         AND r.task_run_id = i.task_run_id
         AND r.execution_count = i.execution_count
         AND r.invocation_id = i.invocation_id
        """
    )
    spark.sql(
        f"""
        CREATE OR REPLACE VIEW {node_view}
        COMMENT 'Sanitized dbt node health; messages and compiled SQL are excluded'
        AS WITH complete_attempts AS (
          SELECT
            i.workspace_id,
            i.job_id,
            i.job_run_id,
            i.repair_count,
            i.task_run_id,
            i.execution_count,
            i.invocation_id
          FROM {registry} AS r
          INNER JOIN {invocations} AS i
            ON r.workspace_id = i.workspace_id
           AND r.job_id = i.job_id
           AND r.job_run_id = i.job_run_id
           AND r.repair_count = i.repair_count
           AND r.task_run_id = i.task_run_id
           AND r.execution_count = i.execution_count
           AND r.invocation_id = i.invocation_id
          LEFT JOIN {nodes} AS observed
            ON observed.workspace_id = i.workspace_id
           AND observed.job_id = i.job_id
           AND observed.job_run_id = i.job_run_id
           AND observed.repair_count = i.repair_count
           AND observed.task_run_id = i.task_run_id
           AND observed.execution_count = i.execution_count
           AND observed.invocation_id = i.invocation_id
          WHERE r.capture_status = 'COMPLETE'
            AND r.archive_sha256 IS NOT NULL
          GROUP BY
            i.workspace_id,
            i.job_id,
            i.job_run_id,
            i.repair_count,
            i.task_run_id,
            i.execution_count,
            i.invocation_id,
            i.total_nodes
          HAVING count(observed.unique_id) = i.total_nodes
        )
        SELECT
          n.workspace_id,
          n.job_id,
          n.job_run_id,
          n.repair_count,
          n.task_run_id,
          n.execution_count,
          n.invocation_id,
          n.unique_id,
          n.resource_type,
          n.node_name,
          n.status,
          n.execution_seconds,
          n.compile_seconds,
          n.execute_seconds,
          n.failures,
          n.rows_affected,
          n.ingested_at
        FROM {nodes} AS n
        INNER JOIN complete_attempts AS c
          ON c.workspace_id = n.workspace_id
         AND c.job_id = n.job_id
         AND c.job_run_id = n.job_run_id
         AND c.repair_count = n.repair_count
         AND c.task_run_id = n.task_run_id
         AND c.execution_count = n.execution_count
         AND c.invocation_id = n.invocation_id
        """
    )
    _create_lakeflow_views_best_effort(
        spark,
        context=context,
        run_view=run_view,
        lakeflow_view=lakeflow_view,
        lakeflow_task_view=lakeflow_task_view,
        combined_view=combined_view,
    )


def _create_lakeflow_views_best_effort(
    spark: Any,
    *,
    context: CaptureContext | CollectorConfig,
    run_view: str,
    lakeflow_view: str,
    lakeflow_task_view: str,
    combined_view: str,
) -> bool:
    """Create scoped system-table views without making artifact capture depend on broad access."""

    source_job_id = (
        context.source_job_id if isinstance(context, CollectorConfig) else context.job_id
    )
    source_task_key = (
        context.source_task_key if isinstance(context, CollectorConfig) else context.task_key
    )
    if not _SAFE_IDENTIFIER.fullmatch(source_task_key):
        raise ArtifactValidationError("RUNTIME_PARAMETER_INVALID")
    try:
        spark.sql(
            f"""
            CREATE OR REPLACE VIEW {lakeflow_view}
            COMMENT 'One sanitized row per configured Lakeflow source job run'
            AS WITH slices AS (
              SELECT
                try_cast(t.workspace_id AS BIGINT) AS workspace_id,
                try_cast(t.job_id AS BIGINT) AS job_id,
                try_cast(t.run_id AS BIGINT) AS run_id,
                t.period_start_time,
                t.period_end_time,
                t.result_state,
                t.termination_code,
                t.trigger_type,
                t.run_type
              FROM system.lakeflow.job_run_timeline AS t
              WHERE t.period_start_time >= current_timestamp() - INTERVAL 365 DAYS
                AND try_cast(t.workspace_id AS BIGINT) = {context.workspace_id}
                AND try_cast(t.job_id AS BIGINT) = {source_job_id}
                AND try_cast(t.run_id AS BIGINT) IS NOT NULL
            ),
            spans AS (
              SELECT
                workspace_id,
                job_id,
                run_id,
                min(period_start_time) AS started_at,
                max(period_end_time) AS ended_at,
                sum(unix_timestamp(period_end_time) - unix_timestamp(period_start_time))
                  AS active_seconds
              FROM slices
              GROUP BY workspace_id, job_id, run_id
            ),
            terminal AS (
              SELECT
                workspace_id,
                job_id,
                run_id,
                result_state,
                termination_code,
                trigger_type,
                run_type
              FROM slices
              WHERE result_state IS NOT NULL
              QUALIFY row_number() OVER (
                PARTITION BY workspace_id, job_id, run_id
                ORDER BY period_end_time DESC
              ) = 1
            )
            SELECT
              s.workspace_id,
              s.job_id,
              s.run_id,
              s.started_at,
              s.ended_at,
              s.active_seconds,
              t.result_state,
              t.termination_code,
              t.trigger_type,
              t.run_type
            FROM spans AS s
            LEFT JOIN terminal AS t
              USING (workspace_id, job_id, run_id)
            """
        )
        spark.sql(
            f"""
            CREATE OR REPLACE VIEW {lakeflow_task_view}
            COMMENT 'One sanitized row per configured dbt task run from system tables'
            AS WITH slices AS (
              SELECT
                try_cast(t.workspace_id AS BIGINT) AS workspace_id,
                try_cast(t.job_id AS BIGINT) AS job_id,
                try_cast(t.job_run_id AS BIGINT) AS job_run_id,
                try_cast(t.run_id AS BIGINT) AS task_run_id,
                t.task_key,
                t.period_start_time,
                t.period_end_time,
                t.result_state,
                t.termination_code,
                t.termination_type
              FROM system.lakeflow.job_task_run_timeline AS t
              WHERE t.period_start_time >= current_timestamp() - INTERVAL 365 DAYS
                AND try_cast(t.workspace_id AS BIGINT) = {context.workspace_id}
                AND try_cast(t.job_id AS BIGINT) = {source_job_id}
                AND t.task_key = '{source_task_key}'
                AND try_cast(t.job_run_id AS BIGINT) IS NOT NULL
                AND try_cast(t.run_id AS BIGINT) IS NOT NULL
            ),
            spans AS (
              SELECT
                workspace_id,
                job_id,
                job_run_id,
                task_run_id,
                task_key,
                min(period_start_time) AS started_at,
                max(period_end_time) AS ended_at,
                sum(unix_timestamp(period_end_time) - unix_timestamp(period_start_time))
                  AS active_seconds
              FROM slices
              GROUP BY workspace_id, job_id, job_run_id, task_run_id, task_key
            ),
            terminal AS (
              SELECT
                workspace_id,
                job_id,
                job_run_id,
                task_run_id,
                result_state,
                termination_code,
                termination_type
              FROM slices
              WHERE result_state IS NOT NULL
              QUALIFY row_number() OVER (
                PARTITION BY workspace_id, job_id, job_run_id, task_run_id
                ORDER BY period_end_time DESC
              ) = 1
            )
            SELECT
              s.workspace_id,
              s.job_id,
              s.job_run_id,
              s.task_run_id,
              s.task_key,
              s.started_at,
              s.ended_at,
              s.active_seconds,
              t.result_state,
              t.termination_code,
              t.termination_type
            FROM spans AS s
            LEFT JOIN terminal AS t
              USING (workspace_id, job_id, job_run_id, task_run_id)
            """
        )
        spark.sql(
            f"""
            CREATE OR REPLACE VIEW {combined_view}
            COMMENT 'Independent Lakeflow run health enriched with sanitized dbt evidence'
            AS SELECT
              l.workspace_id,
              l.job_id,
              l.run_id AS job_run_id,
              l.started_at,
              l.ended_at,
              l.active_seconds,
              l.result_state,
              l.termination_code,
              l.trigger_type,
              l.run_type,
              t.task_run_id AS native_task_run_id,
              t.result_state AS task_result_state,
              t.termination_code AS task_termination_code,
              t.termination_type AS task_termination_type,
              d.repair_count,
              d.task_run_id,
              d.execution_count,
              d.capture_status,
              d.capture_error_code,
              d.staging_cleanup_status,
              d.staging_cleanup_error_code,
              d.invocation_id,
              d.invocation_status,
              d.elapsed_seconds AS dbt_elapsed_seconds,
              d.total_nodes,
              d.success_nodes,
              d.warning_nodes,
              d.failed_nodes,
              d.skipped_nodes,
              CASE
                WHEN d.job_run_id IS NOT NULL THEN d.capture_status
                WHEN l.result_state IS NOT NULL THEN 'MISSING'
                ELSE 'PENDING'
              END AS evidence_status
            FROM {lakeflow_view} AS l
            LEFT JOIN {lakeflow_task_view} AS t
              ON t.workspace_id = l.workspace_id
             AND t.job_id = l.job_id
             AND t.job_run_id = l.run_id
            LEFT JOIN {run_view} AS d
              ON d.workspace_id = l.workspace_id
             AND d.job_id = l.job_id
             AND d.job_run_id = l.run_id
             AND d.task_run_id = t.task_run_id
            """
        )
    except Exception:
        print("Optional Lakeflow views were not refreshed: SYSTEM_LAKEFLOW_VIEW_UNAVAILABLE")
        return False
    return True


def _read_staged_file(
    path: str,
    *,
    required: bool,
) -> bytes | None:
    try:
        before = _validate_staging_path(
            path,
            final_directory=False,
            invalid_code="STAGED_ARTIFACT_TYPE_INVALID",
        )
        chunks: list[bytes] = []
        total = 0
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise ArtifactValidationError("STAGED_ARTIFACT_CHANGED_DURING_READ")
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise ArtifactValidationError("STAGED_ARTIFACT_SIZE_INVALID")
                chunks.append(chunk)
            after = os.fstat(stream.fileno())
    except FileNotFoundError:
        if required:
            raise ArtifactValidationError("STAGED_ARTIFACT_MISSING") from None
        return None
    except ArtifactValidationError:
        raise
    except OSError:
        raise ArtifactValidationError("STAGED_ARTIFACT_READ_ERROR") from None
    if before.st_size != total or (before.st_size, before.st_mtime_ns) != (
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ArtifactValidationError("STAGED_ARTIFACT_CHANGED_DURING_READ")
    return b"".join(chunks)


def _staged_archive(context: CaptureContext) -> bytes:
    root = _staging_root(context)
    try:
        _validate_staging_path(
            root,
            final_directory=True,
            invalid_code="STAGED_ARTIFACT_TYPE_INVALID",
        )
        _validate_staging_path(
            f"{root}/target",
            final_directory=True,
            invalid_code="STAGED_ARTIFACT_TYPE_INVALID",
        )
    except FileNotFoundError:
        raise ArtifactValidationError("STAGED_ARTIFACT_NOT_PRODUCED") from None
    staged_members = (
        ("target/manifest.json", f"{root}/target/manifest.json"),
        ("target/run_results.json", f"{root}/target/run_results.json"),
    )
    members: list[tuple[str, bytes]] = []
    total = 0
    for archive_name, source_path in staged_members:
        payload = _read_staged_file(source_path, required=False)
        if payload is None:
            continue
        total += len(payload)
        if total > MAX_ARCHIVE_BYTES:
            raise ArtifactValidationError("STAGED_ARTIFACT_SIZE_INVALID")
        members.append((archive_name, payload))

    if not members:
        raise ArtifactValidationError("STAGED_ARTIFACT_NOT_PRODUCED")

    stream = BytesIO()
    with (
        gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for archive_name, payload in members:
            info = tarfile.TarInfo(name=archive_name)
            info.size = len(payload)
            info.mode = 0o600
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, BytesIO(payload))
    data = stream.getvalue()
    if not data or len(data) > MAX_ARCHIVE_BYTES:
        raise ArtifactValidationError("ARCHIVE_SIZE_INVALID")
    return data


def _enum_text(value: object) -> str:
    raw_value = getattr(value, "value", value)
    if raw_value is None:
        return "unknown"
    text = str(raw_value).strip().lower()
    if not text or len(text) > 128 or any(ord(character) < 32 for character in text):
        return "unknown"
    return text


def _task_result_state(task: Any) -> str:
    legacy_result = getattr(getattr(task, "state", None), "result_state", None)
    if legacy_result is not None:
        return _enum_text(legacy_result)

    termination_code = _enum_text(
        getattr(
            getattr(getattr(task, "status", None), "termination_details", None),
            "code",
            None,
        )
    )
    return {
        "success": "success",
        "run_execution_error": "failed",
        "timed_out": "timedout",
        "canceled": "canceled",
        "cancelled": "canceled",
    }.get(termination_code, termination_code)


def _numeric_staging_directories(
    parent_path: str,
    key: str,
) -> list[tuple[int, str]]:
    pattern = re.compile(rf"^{re.escape(key)}=([0-9]+)$")
    entries: list[tuple[int, str]] = []
    try:
        _validate_staging_path(
            parent_path,
            final_directory=True,
            invalid_code="STAGING_DIRECTORY_TYPE_INVALID",
        )
        scanned_entries = 0
        for entry in os.scandir(parent_path):
            scanned_entries += 1
            if scanned_entries > _MAX_STAGING_ENTRIES:
                raise ArtifactValidationError("STAGING_DIRECTORY_LIMIT_EXCEEDED")
            match = pattern.fullmatch(entry.name)
            if match is None:
                continue
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                raise ArtifactValidationError("STAGING_DIRECTORY_TYPE_INVALID")
            value = int(match.group(1))
            minimum = 0 if key in {"repair_count", "execution_count"} else 1
            if value < minimum:
                raise ArtifactValidationError("RUN_IDENTIFIER_INVALID")
            entries.append((value, entry.path))
    except FileNotFoundError:
        return []
    except ArtifactValidationError:
        raise
    except OSError:
        raise ArtifactValidationError("STAGING_LIST_ERROR") from None
    return sorted(entries)


def _task_uses_staging(task: Any, config: CollectorConfig) -> bool:
    expected_volume = f"/Volumes/{config.catalog}/{config.schema}/{config.staging_volume}/"
    required_path_segments = (
        "workspace_id=",
        "job_id=",
        "job_run_id=",
        "repair_count=",
        "task_run_id=",
        "execution_count=",
        "/target",
    )
    commands = getattr(getattr(task, "dbt_task", None), "commands", None) or []
    return any(
        isinstance(command, str)
        and "--target-path" in command
        and expected_volume in command
        and all(segment in command for segment in required_path_segments)
        for command in commands
    )


def _completed_capture_contexts(
    client: WorkspaceClient,
    config: CollectorConfig,
    terminal_attempts: frozenset[AttemptKey] = frozenset(),
    *,
    now: datetime | None = None,
) -> CaptureDiscovery:
    """Return staged attempts and instrumented tasks whose staging is absent."""

    observed_at = now or datetime.now(timezone.utc)
    start_time_from = int((observed_at - timedelta(days=config.lookback_days)).timestamp() * 1000)
    contexts: list[tuple[int, int, CaptureContext]] = []
    gaps: list[DiscoveryGap] = []
    seen_attempts: set[AttemptKey] = set()
    terminal_task_runs = {
        (attempt.job_run_id, attempt.task_run_id) for attempt in terminal_attempts
    }

    try:
        runs = client.jobs.list_runs(
            job_id=config.source_job_id,
            completed_only=True,
            expand_tasks=True,
            start_time_from=start_time_from,
        )
        for run in runs:
            if run.job_id != config.source_job_id:
                raise ArtifactValidationError("RUN_SOURCE_MISMATCH")
            parent_run_id = run.run_id
            if parent_run_id is None:
                continue
            source_tasks = [
                task
                for task in run.tasks or []
                if task.task_key == config.source_task_key and task.run_id is not None
            ]
            task_states = {task.run_id: _task_result_state(task) for task in source_tasks}
            authorized_task_run_ids = set(task_states)
            for repair in getattr(run, "repair_history", None) or []:
                authorized_task_run_ids.update(repair.task_run_ids or [])
            run_root = (
                f"/Volumes/{config.catalog}/{config.schema}/{config.staging_volume}/"
                f"workspace_id={config.workspace_id}/job_id={config.source_job_id}/"
                f"job_run_id={parent_run_id}"
            )
            discovered_task_run_ids: set[int] = set()
            for repair_count, repair_path in _numeric_staging_directories(run_root, "repair_count"):
                for task_run_id, task_path in _numeric_staging_directories(
                    repair_path, "task_run_id"
                ):
                    if task_run_id not in authorized_task_run_ids:
                        try:
                            detailed = client.jobs.get_run(
                                run_id=parent_run_id,
                                include_history=True,
                            )
                        except DatabricksError:
                            raise ArtifactValidationError("RUN_DETAIL_API_ERROR") from None
                        authorized_task_run_ids.update(
                            task.run_id
                            for task in detailed.tasks or []
                            if task.task_key == config.source_task_key and task.run_id is not None
                        )
                        for repair in detailed.repair_history or []:
                            authorized_task_run_ids.update(repair.task_run_ids or [])
                    if task_run_id not in authorized_task_run_ids:
                        raise ArtifactValidationError("STAGING_TASK_RUN_UNCORRELATED")
                    for execution_count, _ in _numeric_staging_directories(
                        task_path, "execution_count"
                    ):
                        context = CaptureContext(
                            workspace_id=config.workspace_id,
                            job_id=config.source_job_id,
                            job_run_id=parent_run_id,
                            task_run_id=task_run_id,
                            repair_count=repair_count,
                            execution_count=execution_count,
                            task_key=config.source_task_key,
                            upstream_result_state=task_states.get(task_run_id, "unknown"),
                            catalog=config.catalog,
                            schema=config.schema,
                            volume=config.volume,
                            staging_volume=config.staging_volume,
                        )
                        if context.attempt_key in seen_attempts:
                            raise ArtifactValidationError("DUPLICATE_ATTEMPT_STAGING")
                        seen_attempts.add(context.attempt_key)
                        discovered_task_run_ids.add(task_run_id)
                        contexts.append(
                            (
                                run.start_time or 0,
                                task_run_id,
                                context,
                            )
                        )
            for task in source_tasks:
                task_run_id = task.run_id
                if (
                    task_run_id is not None
                    and _task_uses_staging(task, config)
                    and task_run_id not in discovered_task_run_ids
                    and (parent_run_id, task_run_id) not in terminal_task_runs
                ):
                    gaps.append(
                        DiscoveryGap(
                            job_run_id=parent_run_id,
                            task_run_id=task_run_id,
                        )
                    )
    except DatabricksError:
        raise ArtifactValidationError("RUN_LIST_API_ERROR") from None

    contexts.sort(key=lambda item: (item[0], item[1]))
    return CaptureDiscovery(
        contexts=tuple(context for _, _, context in contexts),
        gaps=tuple(gaps),
    )


def _registry_capture_state(
    spark: Any,
    config: CollectorConfig,
) -> RegistryCaptureState:
    registry = _object_name(config, "dbt_artifact_registry")
    invocations = _object_name(config, "dbt_invocations")
    nodes = _object_name(config, "dbt_node_results")
    # Quarantined means the content-addressed raw archive was persisted but rejected by
    # the allowlisted parser. It remains terminal until an explicit, reviewed
    # parser migration reprocesses that archive; scheduled sweeps must not
    # re-download and alert on the same evidence forever.
    rows = spark.sql(
        f"""
        WITH complete_facts AS (
          SELECT
            i.workspace_id,
            i.job_id,
            i.job_run_id,
            i.repair_count,
            i.task_run_id,
            i.execution_count,
            i.invocation_id
          FROM {invocations} AS i
          LEFT JOIN {nodes} AS n
            ON n.workspace_id = i.workspace_id
           AND n.job_id = i.job_id
           AND n.job_run_id = i.job_run_id
           AND n.repair_count = i.repair_count
           AND n.task_run_id = i.task_run_id
           AND n.execution_count = i.execution_count
           AND n.invocation_id = i.invocation_id
          GROUP BY
            i.workspace_id,
            i.job_id,
            i.job_run_id,
            i.repair_count,
            i.task_run_id,
            i.execution_count,
            i.invocation_id,
            i.total_nodes
          HAVING count(n.unique_id) = i.total_nodes
        )
        SELECT
          r.job_run_id,
          r.repair_count,
          r.task_run_id,
          r.execution_count,
          r.task_key,
          r.upstream_result_state,
          r.capture_status,
          r.captured_at,
          r.staging_cleanup_status,
          CASE
            WHEN r.capture_status = 'NOT_PRODUCED' THEN true
            WHEN r.capture_status = 'QUARANTINED'
             AND r.archive_sha256 IS NOT NULL THEN true
            WHEN r.capture_status = 'COMPLETE'
             AND r.archive_sha256 IS NOT NULL
             AND r.invocation_id IS NOT NULL
             AND EXISTS (
               SELECT 1
               FROM complete_facts AS f
               WHERE f.workspace_id = r.workspace_id
                 AND f.job_id = r.job_id
                 AND f.job_run_id = r.job_run_id
                 AND f.repair_count = r.repair_count
                 AND f.task_run_id = r.task_run_id
                 AND f.execution_count = r.execution_count
                 AND f.invocation_id = r.invocation_id
             ) THEN true
            ELSE false
          END AS is_terminal
        FROM {registry} AS r
        WHERE r.workspace_id = {config.workspace_id}
          AND r.job_id = {config.source_job_id}
        """
    ).collect()
    terminal: set[AttemptKey] = set()
    last_attempted_at: dict[AttemptKey, float] = {}
    cleanup_pending: list[CaptureContext] = []
    for row in rows:
        attempt_key = AttemptKey(
            workspace_id=config.workspace_id,
            job_id=config.source_job_id,
            job_run_id=int(row["job_run_id"]),
            repair_count=int(row["repair_count"]),
            task_run_id=int(row["task_run_id"]),
            execution_count=int(row["execution_count"]),
        )
        if attempt_key in last_attempted_at:
            raise ArtifactValidationError("DUPLICATE_REGISTRY_KEY")
        captured_at = row["captured_at"]
        last_attempted_at[attempt_key] = (
            captured_at.timestamp() if isinstance(captured_at, datetime) else 0.0
        )
        is_terminal = bool(row["is_terminal"])
        if is_terminal:
            terminal.add(attempt_key)
        cleanup_status = str(row["staging_cleanup_status"])
        if cleanup_status not in {"PENDING", "DELETED"}:
            raise ArtifactValidationError("STAGING_CLEANUP_STATE_INVALID")
        if is_terminal and cleanup_status == "PENDING":
            cleanup_pending.append(
                CaptureContext(
                    workspace_id=config.workspace_id,
                    job_id=config.source_job_id,
                    job_run_id=attempt_key.job_run_id,
                    task_run_id=attempt_key.task_run_id,
                    repair_count=attempt_key.repair_count,
                    execution_count=attempt_key.execution_count,
                    task_key=str(row["task_key"]),
                    upstream_result_state=str(row["upstream_result_state"]),
                    catalog=config.catalog,
                    schema=config.schema,
                    volume=config.volume,
                    staging_volume=config.staging_volume,
                )
            )
    cleanup_pending.sort(
        key=lambda context: (
            context.job_run_id,
            context.repair_count,
            context.task_run_id,
            context.execution_count,
        )
    )
    return RegistryCaptureState(
        terminal_attempts=frozenset(terminal),
        last_attempted_at=last_attempted_at,
        cleanup_pending=tuple(cleanup_pending),
    )


def _remote_archive_sha256(path: str) -> str:
    try:
        digest = hashlib.sha256()
        total = 0
        with open(path, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise ArtifactValidationError("ARCHIVE_REMOTE_SIZE_INVALID")
                digest.update(chunk)
    except ArtifactValidationError:
        raise
    except OSError:
        raise ArtifactValidationError("ARCHIVE_REMOTE_READ_ERROR") from None
    return digest.hexdigest()


def _upload_content_addressed(path: str, data: bytes, digest: str) -> None:
    directory = path.rsplit("/", 1)[0]
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    except OSError:
        raise ArtifactValidationError("ARCHIVE_UPLOAD_ERROR") from None

    created = False
    try:
        with open(path, "xb") as stream:
            created = True
            offset = 0
            payload = memoryview(data)
            while offset < len(payload):
                written = stream.write(payload[offset:])
                if written is None or written <= 0:
                    raise ArtifactValidationError("ARCHIVE_UPLOAD_INCOMPLETE")
                offset += written
    except FileExistsError:
        check_existing_hash(_remote_archive_sha256(path), digest)
        return
    except ArtifactValidationError:
        if created:
            with suppress(OSError):
                os.unlink(path)
        raise
    except OSError:
        if created:
            try:
                if _remote_archive_sha256(path) == digest:
                    return
                os.unlink(path)
            except (ArtifactValidationError, OSError):
                pass
        raise ArtifactValidationError("ARCHIVE_UPLOAD_ERROR") from None

    try:
        check_existing_hash(_remote_archive_sha256(path), digest)
    except ArtifactValidationError:
        if created:
            with suppress(OSError):
                os.unlink(path)
        raise


def _delete_staging(context: CaptureContext) -> None:
    root = _staging_root(context)
    visited = 0
    volume_root = f"/Volumes/{context.catalog}/{context.schema}/{context.staging_volume}"
    resolved_root = os.path.realpath(root)

    # Validate every producer-writable identity directory before traversal. In
    # production this prevents an attempt or one of its ancestors from being
    # replaced with a symlink that redirects cleanup outside the governed
    # staging Volume. Unit tests monkeypatch the root to a temporary directory,
    # so the Volume-prefix check is deliberately conditional on the real path.
    if root.startswith(f"{volume_root}/"):
        resolved_volume_root = os.path.realpath(volume_root)
        try:
            if os.path.commonpath((resolved_volume_root, resolved_root)) != resolved_volume_root:
                raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID")
        except ValueError:
            raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID") from None

        current_path = volume_root
        for component in root.removeprefix(f"{volume_root}/").split("/"):
            current_path = os.path.join(current_path, component)
            try:
                metadata = os.lstat(current_path)
            except FileNotFoundError:
                return
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID")

    def delete_tree(path: str, depth: int) -> None:
        nonlocal visited
        if depth > _MAX_STAGING_DEPTH:
            raise ArtifactValidationError("STAGING_CLEANUP_DEPTH_EXCEEDED")
        try:
            try:
                contained = (
                    os.path.commonpath((resolved_root, os.path.realpath(path))) == resolved_root
                )
            except ValueError:
                raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID") from None
            if not contained:
                raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID")
            metadata = os.lstat(path)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID")
            entries: list[os.DirEntry[str]] = []
            with os.scandir(path) as iterator:
                for entry in iterator:
                    visited += 1
                    if visited > _MAX_STAGING_ENTRIES:
                        raise ArtifactValidationError("STAGING_CLEANUP_ENTRY_LIMIT_EXCEEDED")
                    entries.append(entry)
        except FileNotFoundError:
            return
        for entry in entries:
            if entry.is_symlink():
                raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID")
            if entry.is_dir(follow_symlinks=False):
                delete_tree(entry.path, depth + 1)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise ArtifactValidationError("STAGING_CLEANUP_TYPE_INVALID")
            with suppress(FileNotFoundError):
                os.unlink(entry.path)
        with suppress(FileNotFoundError):
            os.rmdir(path)

    try:
        delete_tree(root, 0)
    except ArtifactValidationError:
        raise
    except OSError:
        raise ArtifactValidationError("STAGING_CLEANUP_ERROR") from None


def _record_staging_cleanup(
    spark: Any,
    context: CaptureContext,
    *,
    deleted: bool,
    error_code: str | None,
) -> None:
    if deleted == (error_code is not None):
        raise ArtifactValidationError("STAGING_CLEANUP_STATE_INVALID")
    if error_code is not None and not _SAFE_ERROR_CODE.fullmatch(error_code):
        raise ArtifactValidationError("STAGING_CLEANUP_STATE_INVALID")
    status = "DELETED" if deleted else "PENDING"
    deleted_expression = "current_timestamp()" if deleted else "staging_deleted_at"
    error_expression = "NULL" if error_code is None else f"'{error_code}'"
    registry = _object_name(context, "dbt_artifact_registry")
    spark.sql(
        f"""
        UPDATE {registry}
        SET staging_cleanup_status = '{status}',
            staging_cleanup_error_code = {error_expression},
            staging_cleanup_updated_at = current_timestamp(),
            staging_deleted_at = {deleted_expression}
        WHERE workspace_id = {context.workspace_id}
          AND job_id = {context.job_id}
          AND job_run_id = {context.job_run_id}
          AND repair_count = {context.repair_count}
          AND task_run_id = {context.task_run_id}
          AND execution_count = {context.execution_count}
          AND capture_status IN ('COMPLETE', 'QUARANTINED', 'NOT_PRODUCED')
        """
    )
    rows = spark.sql(
        f"""
        SELECT staging_cleanup_status, staging_cleanup_error_code
        FROM {registry}
        WHERE workspace_id = {context.workspace_id}
          AND job_id = {context.job_id}
          AND job_run_id = {context.job_run_id}
          AND repair_count = {context.repair_count}
          AND task_run_id = {context.task_run_id}
          AND execution_count = {context.execution_count}
        """
    ).collect()
    if len(rows) != 1 or str(rows[0]["staging_cleanup_status"]) != status:
        raise ArtifactValidationError("STAGING_CLEANUP_STATE_INVALID")
    if rows[0]["staging_cleanup_error_code"] != error_code:
        raise ArtifactValidationError("STAGING_CLEANUP_STATE_INVALID")


def _existing_hash(spark: Any, context: CaptureContext) -> str | None:
    registry = _object_name(context, "dbt_artifact_registry")
    rows = spark.sql(
        f"""
        SELECT archive_sha256
        FROM {registry}
        WHERE workspace_id = {context.workspace_id}
          AND job_id = {context.job_id}
          AND job_run_id = {context.job_run_id}
          AND repair_count = {context.repair_count}
          AND task_run_id = {context.task_run_id}
          AND execution_count = {context.execution_count}
        """
    ).collect()
    if len(rows) > 1:
        raise ArtifactValidationError("DUPLICATE_REGISTRY_KEY")
    return None if not rows else rows[0]["archive_sha256"]


def _merge_rows(
    spark: Any,
    *,
    target: str,
    view_name: str,
    schema: str,
    rows: list[tuple[Any, ...]],
    keys: tuple[str, ...],
    matched_update_condition: str | None = None,
) -> None:
    frame = spark.createDataFrame(rows, schema=schema)
    frame.createOrReplaceTempView(view_name)
    predicate = " AND ".join(f"target.{key} = source.{key}" for key in keys)
    matched_clause = "WHEN MATCHED THEN UPDATE SET *"
    if matched_update_condition is not None:
        matched_clause = f"WHEN MATCHED AND {matched_update_condition} THEN UPDATE SET *"
    spark.sql(
        f"""
        MERGE INTO {target} AS target
        USING {view_name} AS source
          ON {predicate}
        {matched_clause}
        WHEN NOT MATCHED THEN INSERT *
        """
    )


def _registry_row(
    context: CaptureContext,
    *,
    captured_at: datetime,
    capture_status: str,
    capture_error_code: str | None,
    path: str | None = None,
    digest: str | None = None,
    archive_bytes: int | None = None,
    scan: ArchiveScan | None = None,
    parsed: ParsedArtifacts | None = None,
) -> tuple[Any, ...]:
    return (
        context.workspace_id,
        context.job_id,
        context.job_run_id,
        context.repair_count,
        context.task_run_id,
        context.execution_count,
        context.task_key,
        context.upstream_result_state,
        capture_status,
        capture_error_code,
        captured_at,
        "PENDING",
        None,
        captured_at,
        None,
        path,
        digest,
        archive_bytes,
        None if scan is None else scan.file_count,
        None if scan is None else scan.total_uncompressed_bytes,
        None if parsed is None else parsed.invocation_id,
        None if parsed is None else parsed.dbt_version,
        None if parsed is None else parsed.adapter_type,
        None if parsed is None else parsed.manifest_schema_version,
        None if parsed is None else parsed.run_results_schema_version,
        PARSER_VERSION,
    )


def _upsert_registry(spark: Any, context: CaptureContext, row: tuple[Any, ...]) -> None:
    _merge_rows(
        spark,
        target=_object_name(context, "dbt_artifact_registry"),
        view_name="_dbt_observability_registry_source",
        schema=_REGISTRY_SCHEMA,
        rows=[row],
        keys=(
            "workspace_id",
            "job_id",
            "job_run_id",
            "repair_count",
            "task_run_id",
            "execution_count",
        ),
        matched_update_condition=(
            "(target.archive_sha256 IS NULL AND source.archive_sha256 IS NOT NULL) "
            "OR (target.capture_status IN ('RETRYABLE_ERROR', 'UPLOAD_FAILED') "
            "AND source.capture_status IN "
            "('RETRYABLE_ERROR', 'UPLOAD_FAILED', 'COMPLETE', 'QUARANTINED', "
            "'NOT_PRODUCED'))"
        ),
    )


def _upsert_parsed_facts(
    spark: Any,
    context: CaptureContext,
    parsed: ParsedArtifacts,
    ingested_at: datetime,
) -> None:
    invocation_row = (
        context.workspace_id,
        context.job_id,
        context.job_run_id,
        context.repair_count,
        context.task_run_id,
        context.execution_count,
        parsed.invocation_id,
        parsed.generated_at,
        parsed.dbt_version,
        parsed.adapter_type,
        parsed.command,
        parsed.invocation_status,
        parsed.elapsed_seconds,
        parsed.total_nodes,
        parsed.success_nodes,
        parsed.warning_nodes,
        parsed.failed_nodes,
        parsed.skipped_nodes,
        parsed.manifest_sha256,
        PARSER_VERSION,
        ingested_at,
    )
    _merge_rows(
        spark,
        target=_object_name(context, "dbt_invocations"),
        view_name="_dbt_observability_invocation_source",
        schema=_INVOCATION_SCHEMA,
        rows=[invocation_row],
        keys=(
            "workspace_id",
            "job_id",
            "job_run_id",
            "repair_count",
            "task_run_id",
            "execution_count",
            "invocation_id",
        ),
    )

    node_rows = [
        (
            context.workspace_id,
            context.job_id,
            context.job_run_id,
            context.repair_count,
            context.task_run_id,
            context.execution_count,
            parsed.invocation_id,
            node.unique_id,
            node.resource_type,
            node.node_name,
            node.status,
            node.execution_seconds,
            node.compile_seconds,
            node.execute_seconds,
            node.failures,
            node.rows_affected,
            ingested_at,
        )
        for node in parsed.nodes
    ]
    _merge_rows(
        spark,
        target=_object_name(context, "dbt_node_results"),
        view_name="_dbt_observability_node_source",
        schema=_NODE_SCHEMA,
        rows=node_rows,
        keys=(
            "workspace_id",
            "job_id",
            "job_run_id",
            "repair_count",
            "task_run_id",
            "execution_count",
            "invocation_id",
            "unique_id",
        ),
    )


def _capture_one(
    spark: Any,
    context: CaptureContext,
) -> ParsedArtifacts:
    captured_at = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        data = _staged_archive(context)
    except ArtifactValidationError as exc:
        capture_status = (
            "NOT_PRODUCED" if exc.code == "STAGED_ARTIFACT_NOT_PRODUCED" else "RETRYABLE_ERROR"
        )
        _upsert_registry(
            spark,
            context,
            _registry_row(
                context,
                captured_at=captured_at,
                capture_status=capture_status,
                capture_error_code=exc.code,
            ),
        )
        raise
    digest = archive_sha256(data)
    scan: ArchiveScan | None = None
    parsed: ParsedArtifacts | None = None
    validation_error: ArtifactValidationError | None = None
    try:
        scan = scan_archive(data)
        parsed = parse_artifacts(scan)
    except ArtifactValidationError as exc:
        validation_error = exc

    path = build_archive_path(
        catalog=context.catalog,
        schema=context.schema,
        volume=context.volume,
        workspace_id=context.workspace_id,
        job_id=context.job_id,
        job_run_id=context.job_run_id,
        repair_count=context.repair_count,
        task_run_id=context.task_run_id,
        execution_count=context.execution_count,
        digest=digest,
        quarantined=validation_error is not None,
    )
    check_existing_hash(_existing_hash(spark, context), digest)
    try:
        _upload_content_addressed(path, data, digest)
    except ArtifactValidationError as exc:
        _upsert_registry(
            spark,
            context,
            _registry_row(
                context,
                captured_at=captured_at,
                capture_status="UPLOAD_FAILED",
                capture_error_code=exc.code,
            ),
        )
        raise

    if validation_error is not None:
        _upsert_registry(
            spark,
            context,
            _registry_row(
                context,
                captured_at=captured_at,
                capture_status="QUARANTINED",
                capture_error_code=validation_error.code,
                path=path,
                digest=digest,
                archive_bytes=len(data),
                scan=scan,
            ),
        )
        raise validation_error

    if scan is None or parsed is None:
        raise RuntimeError("dbt artifact parser invariant failed")

    # Facts must exist before the registry becomes terminal. If a MERGE fails,
    # the next sweep sees a non-terminal row and safely retries this task run.
    _upsert_parsed_facts(spark, context, parsed, captured_at)
    _upsert_registry(
        spark,
        context,
        _registry_row(
            context,
            captured_at=captured_at,
            capture_status="COMPLETE",
            capture_error_code=None,
            path=path,
            digest=digest,
            archive_bytes=len(data),
            scan=scan,
            parsed=parsed,
        ),
    )
    return parsed


def main() -> None:
    client = WorkspaceClient()
    config = CollectorConfig.from_widgets(workspace_id=client.get_workspace_id())
    spark = _spark_session()
    _ensure_delta_objects(spark, config)
    registry_state = _registry_capture_state(spark, config)

    try:
        discovery = _completed_capture_contexts(
            client,
            config,
            registry_state.terminal_attempts,
        )
    except ArtifactValidationError:
        _create_curated_views(spark, config)
        raise RuntimeError("completed source dbt runs could not be enumerated") from None

    contexts = list(discovery.contexts)
    incomplete_contexts = [
        context
        for context in contexts
        if context.attempt_key not in registry_state.terminal_attempts
    ]
    # Never-seen runs are captured before retries so a permanent historical gap
    # cannot starve fresh evidence. Retried gaps are least-recently-attempted first.
    unseen_contexts = [
        context
        for context in incomplete_contexts
        if context.attempt_key not in registry_state.last_attempted_at
    ]
    retry_contexts = [
        context
        for context in incomplete_contexts
        if context.attempt_key in registry_state.last_attempted_at
    ]
    retry_contexts.sort(key=lambda context: registry_state.last_attempted_at[context.attempt_key])
    selected_contexts = (unseen_contexts + retry_contexts)[: config.max_task_runs_per_sweep]
    captured = 0
    cleaned = 0
    failures: list[tuple[str, str]] = []

    for gap in discovery.gaps:
        failures.append((f"job_run_id={gap.job_run_id}", "STAGING_NOT_PRODUCED"))
        print(
            "dbt staging was not produced "
            f"for job_run_id={gap.job_run_id}, task_run_id={gap.task_run_id}, "
            "error_code=STAGING_NOT_PRODUCED"
        )

    for context in selected_contexts:
        try:
            parsed = _capture_one(spark, context)
        except ArtifactValidationError as exc:
            failures.append((f"task_run_id={context.task_run_id}", exc.code))
            print(
                "dbt artifact capture incomplete "
                f"for task_run_id={context.task_run_id}, "
                f"execution_count={context.execution_count}, error_code={exc.code}"
            )
        except Exception:
            failures.append((f"task_run_id={context.task_run_id}", "UNEXPECTED_CAPTURE_ERROR"))
            print(
                "dbt artifact capture incomplete "
                f"for task_run_id={context.task_run_id}, "
                "error_code=UNEXPECTED_CAPTURE_ERROR"
            )
        else:
            captured += 1
            print(
                "Captured sanitized dbt evidence "
                f"for job_run_id={context.job_run_id}, "
                f"task_run_id={context.task_run_id}, nodes={parsed.total_nodes}, "
                "capture_status=COMPLETE"
            )

    # Re-read durable state after capture so cleanup runs for COMPLETE,
    # QUARANTINED, and NOT_PRODUCED rows, including rows left pending by a
    # previous collector crash. Capture is never repeated merely to retry cleanup.
    cleanup_state = _registry_capture_state(spark, config)
    for context in cleanup_state.cleanup_pending:
        try:
            _delete_staging(context)
            _record_staging_cleanup(
                spark,
                context,
                deleted=True,
                error_code=None,
            )
        except ArtifactValidationError as exc:
            with suppress(Exception):
                _record_staging_cleanup(
                    spark,
                    context,
                    deleted=False,
                    error_code=exc.code,
                )
            failures.append((f"task_run_id={context.task_run_id}", exc.code))
            print(
                "dbt staging cleanup incomplete "
                f"for task_run_id={context.task_run_id}, error_code={exc.code}"
            )
        except Exception:
            failures.append((f"task_run_id={context.task_run_id}", "STAGING_CLEANUP_STATE_ERROR"))
            print(
                "dbt staging cleanup state could not be persisted "
                f"for task_run_id={context.task_run_id}, "
                "error_code=STAGING_CLEANUP_STATE_ERROR"
            )
        else:
            cleaned += 1

    _create_curated_views(spark, config)

    terminal_skipped = len(contexts) - len(incomplete_contexts)
    deferred = len(incomplete_contexts) - len(selected_contexts)
    print(
        "dbt artifact sweep finished "
        f"source_job_id={config.source_job_id}, discovered={len(contexts)}, "
        f"discovery_gaps={len(discovery.gaps)}, "
        f"terminal_skipped={terminal_skipped}, attempted={len(selected_contexts)}, "
        f"captured={captured}, cleaned={cleaned}, failed={len(failures)}, "
        f"deferred={deferred}"
    )
    if failures or deferred:
        gaps = len(failures) + deferred
        raise RuntimeError(f"dbt artifact capture incomplete for {gaps} task run(s)")


if __name__ == "__main__":
    main()
