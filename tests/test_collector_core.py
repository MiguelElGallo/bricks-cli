from __future__ import annotations

import io
import json
import tarfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from observability import collect_dbt_artifacts as collector_notebook
from observability import collector_core
from observability.collector_core import (
    ArtifactValidationError,
    archive_sha256,
    build_archive_path,
    check_existing_hash,
    parse_artifacts,
    scan_archive,
)


def _manifest(*, invocation_id: str = "invocation-1", schema_version: str | None = None) -> dict:
    return {
        "metadata": {
            "dbt_schema_version": schema_version or collector_core.MANIFEST_SCHEMA,
            "dbt_version": "1.11.11",
            "generated_at": "2026-07-14T10:00:00Z",
            "invocation_id": invocation_id,
            "adapter_type": "databricks",
        },
        "nodes": {
            "seed.bricks_cli_dbt.nyc_taxi_trips_seed": {
                "name": "nyc_taxi_trips_seed",
                "resource_type": "seed",
            },
            "model.bricks_cli_dbt.nyc_taxi_trips": {
                "name": "nyc_taxi_trips",
                "resource_type": "model",
                "compiled_code": "select sensitive_raw_value from source",
            },
            "test.bricks_cli_dbt.not_null_nyc_taxi_trips_pickup_at": {
                "name": "not_null_nyc_taxi_trips_pickup_at",
                "resource_type": "test",
            },
            "test.bricks_cli_dbt.not_null_nyc_taxi_trips_dropoff_at": {
                "name": "not_null_nyc_taxi_trips_dropoff_at",
                "resource_type": "test",
            },
        },
    }


def _run_results(*, invocation_id: str = "invocation-1", schema_version: str | None = None) -> dict:
    def result(unique_id: str, status: str, execution_time: float, rows: int | None) -> dict:
        response = {} if rows is None else {"rows_affected": rows, "raw_response": "omit me"}
        return {
            "unique_id": unique_id,
            "status": status,
            "execution_time": execution_time,
            "timing": [
                {
                    "name": "compile",
                    "started_at": "2026-07-14T10:00:00Z",
                    "completed_at": "2026-07-14T10:00:01Z",
                },
                {
                    "name": "execute",
                    "started_at": "2026-07-14T10:00:01Z",
                    "completed_at": "2026-07-14T10:00:03Z",
                },
            ],
            "failures": 0 if status == "pass" else None,
            "adapter_response": response,
            "message": "sensitive free-form database error text",
            "compiled_code": "select sensitive_raw_value from source",
        }

    return {
        "metadata": {
            "dbt_schema_version": schema_version or collector_core.RUN_RESULTS_SCHEMA,
            "dbt_version": "1.11.11",
            "generated_at": "2026-07-14T10:00:04Z",
            "invocation_id": invocation_id,
        },
        "args": {"which": "build", "vars": "do not persist"},
        "elapsed_time": 4.0,
        "results": [
            result("seed.bricks_cli_dbt.nyc_taxi_trips_seed", "success", 1.0, 100),
            result("model.bricks_cli_dbt.nyc_taxi_trips", "success", 2.0, -1),
            result("test.bricks_cli_dbt.not_null_nyc_taxi_trips_pickup_at", "pass", 0.5, 0),
            result("test.bricks_cli_dbt.not_null_nyc_taxi_trips_dropoff_at", "pass", 0.5, 0),
        ],
    }


def _archive(files: list[tuple[str, bytes]]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, payload in files:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return stream.getvalue()


def _valid_archive(**overrides: dict) -> bytes:
    manifest = overrides.get("manifest", _manifest())
    run_results = overrides.get("run_results", _run_results())
    return _archive(
        [
            ("target/manifest.json", json.dumps(manifest).encode()),
            ("target/run_results.json", json.dumps(run_results).encode()),
            ("logs/dbt.log", b'{"info":{"name":"MainReportVersion"}}\n'),
        ]
    )


def _capture_context(
    *,
    job_run_id: int = 3,
    task_run_id: int = 4,
    repair_count: int = 0,
    execution_count: int = 0,
    upstream_result_state: str = "success",
) -> collector_notebook.CaptureContext:
    return collector_notebook.CaptureContext(
        workspace_id=1,
        job_id=2,
        job_run_id=job_run_id,
        task_run_id=task_run_id,
        repair_count=repair_count,
        execution_count=execution_count,
        task_key="dbt_nyc_taxi",
        upstream_result_state=upstream_result_state,
        catalog="catalog",
        schema="schema",
        volume="volume",
        staging_volume="staging",
    )


def _collector_config() -> collector_notebook.CollectorConfig:
    return collector_notebook.CollectorConfig(
        workspace_id=1,
        source_job_id=2,
        source_task_key="dbt_nyc_taxi",
        lookback_days=59,
        max_task_runs_per_sweep=100,
        catalog="catalog",
        schema="schema",
        volume="volume",
        staging_volume="staging",
    )


def test_combined_health_view_joins_exact_task_attempt() -> None:
    class SqlRecorder:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def sql(self, statement: str) -> None:
            self.statements.append(statement)

    spark = SqlRecorder()

    created = collector_notebook._create_lakeflow_views_best_effort(
        spark,
        context=_collector_config(),
        run_view="catalog.schema.dbt_run_health",
        lakeflow_view="catalog.schema.lakeflow_job_run_health",
        lakeflow_task_view="catalog.schema.lakeflow_dbt_task_run_health",
        combined_view="catalog.schema.dbt_job_health",
    )

    assert created is True
    combined_sql = spark.statements[-1]
    assert "AND d.task_run_id = t.task_run_id" in combined_sql


def test_node_health_view_exposes_only_complete_attempts() -> None:
    class SqlRecorder:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def sql(self, statement: str) -> None:
            self.statements.append(statement)

    spark = SqlRecorder()

    collector_notebook._create_curated_views(spark, _collector_config())

    node_sql = next(
        statement
        for statement in spark.statements
        if "dbt_node_health" in statement and "CREATE OR REPLACE VIEW" in statement
    )
    assert "WHERE r.capture_status = 'COMPLETE'" in node_sql
    assert "AND r.archive_sha256 IS NOT NULL" in node_sql
    assert "HAVING count(observed.unique_id) = i.total_nodes" in node_sql
    assert "AND c.task_run_id = n.task_run_id" in node_sql
    assert "AND c.execution_count = n.execution_count" in node_sql


def _write_staged_artifacts(
    root: Path,
    *,
    manifest: bool = True,
    run_results: bool = True,
) -> None:
    target = root / "target"
    target.mkdir(parents=True)
    if manifest:
        (target / "manifest.json").write_text(json.dumps(_manifest()))
    if run_results:
        (target / "run_results.json").write_text(json.dumps(_run_results()))


def test_supported_archive_is_sanitized_and_complete() -> None:
    data = _valid_archive()
    scan = scan_archive(data)
    parsed = parse_artifacts(scan)

    assert parsed.invocation_id == "invocation-1"
    assert parsed.command == "build"
    assert parsed.adapter_type == "databricks"
    assert parsed.invocation_status == "success"
    assert parsed.total_nodes == 4
    assert parsed.success_nodes == 4
    assert parsed.failed_nodes == 0
    assert parsed.manifest_sha256 == archive_sha256(scan.selected_files["manifest.json"])
    assert parsed.nodes[1].node_name == "nyc_taxi_trips"
    assert parsed.nodes[1].rows_affected == -1
    assert parsed.nodes[1].compile_seconds == 1.0
    assert parsed.nodes[1].execute_seconds == 2.0
    assert not hasattr(parsed.nodes[1], "compiled_code")
    assert not hasattr(parsed.nodes[1], "message")


def test_archive_path_traversal_is_rejected() -> None:
    data = _archive(
        [
            ("../target/manifest.json", json.dumps(_manifest()).encode()),
            ("target/run_results.json", json.dumps(_run_results()).encode()),
        ]
    )

    with pytest.raises(ArtifactValidationError, match="ARCHIVE_PATH_INVALID"):
        scan_archive(data)


def test_duplicate_required_artifact_is_rejected() -> None:
    manifest = json.dumps(_manifest()).encode()
    data = _archive(
        [
            ("first/manifest.json", manifest),
            ("second/manifest.json", manifest),
            ("target/run_results.json", json.dumps(_run_results()).encode()),
        ]
    )

    with pytest.raises(ArtifactValidationError, match="DUPLICATE_REQUIRED_ARTIFACT"):
        scan_archive(data)


def test_missing_run_results_is_rejected_by_scan() -> None:
    data = _archive([("target/manifest.json", json.dumps(_manifest()).encode())])

    with pytest.raises(ArtifactValidationError, match="MISSING_REQUIRED_ARTIFACT"):
        scan_archive(data)


def test_unknown_artifact_schema_is_rejected() -> None:
    data = _valid_archive(
        run_results=_run_results(
            schema_version="https://schemas.getdbt.com/dbt/run-results/v99.json"
        )
    )

    with pytest.raises(ArtifactValidationError, match="UNSUPPORTED_ARTIFACT_SCHEMA"):
        parse_artifacts(scan_archive(data))


def test_invocation_mismatch_is_rejected() -> None:
    data = _valid_archive(run_results=_run_results(invocation_id="different-invocation"))

    with pytest.raises(ArtifactValidationError, match="INVOCATION_ID_MISMATCH"):
        parse_artifacts(scan_archive(data))


def test_unknown_node_status_is_rejected() -> None:
    run_results = _run_results()
    run_results["results"][0]["status"] = "future-unknown-status"

    with pytest.raises(ArtifactValidationError, match="UNSUPPORTED_NODE_STATUS"):
        parse_artifacts(scan_archive(_valid_archive(run_results=run_results)))


def test_no_op_is_success_and_partial_success_is_warning() -> None:
    run_results = _run_results()
    run_results["results"][0]["status"] = "no-op"
    run_results["results"][1]["status"] = "partial success"

    parsed = parse_artifacts(scan_archive(_valid_archive(run_results=run_results)))

    assert parsed.invocation_status == "warning"
    assert parsed.success_nodes == 3
    assert parsed.warning_nodes == 1


def test_member_size_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector_core, "MAX_MEMBER_BYTES", 16)

    with pytest.raises(ArtifactValidationError, match="ARCHIVE_MEMBER_SIZE_EXCEEDED"):
        scan_archive(_valid_archive())


def test_archive_member_count_limit_includes_non_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(collector_core, "MAX_MEMBER_COUNT", 1)
    data = _archive(
        [
            ("target/manifest.json", json.dumps(_manifest()).encode()),
            ("target/run_results.json", json.dumps(_run_results()).encode()),
        ]
    )

    with pytest.raises(ArtifactValidationError, match="ARCHIVE_MEMBER_COUNT_EXCEEDED"):
        scan_archive(data)


def test_archive_path_is_content_addressed_and_allowlisted() -> None:
    digest = archive_sha256(b"archive")
    path = build_archive_path(
        catalog="regulated-catalog",
        schema="dbt_observability_dev",
        volume="dbt_artifacts",
        workspace_id=1,
        job_id=2,
        job_run_id=3,
        repair_count=0,
        task_run_id=4,
        execution_count=0,
        digest=digest,
        quarantined=False,
    )

    assert path.endswith(
        f"repair_count=0/task_run_id=4/execution_count=0/sha256={digest}/dbt-output.tar.gz"
    )
    assert "/raw/" in path


def test_hash_collision_is_rejected_but_retry_is_idempotent() -> None:
    digest = archive_sha256(b"archive")
    check_existing_hash(digest, digest)
    check_existing_hash(None, digest)

    with pytest.raises(ArtifactValidationError, match="ARCHIVE_HASH_COLLISION"):
        check_existing_hash(archive_sha256(b"other"), digest)


def test_content_addressed_posix_write_is_idempotent_and_detects_collision(
    tmp_path: Path,
) -> None:
    payload = b"canonical archive"
    digest = archive_sha256(payload)
    archive_path = tmp_path / f"sha256={digest}" / "dbt-output.tar.gz"

    collector_notebook._upload_content_addressed(str(archive_path), payload, digest)
    collector_notebook._upload_content_addressed(str(archive_path), payload, digest)

    assert archive_path.read_bytes() == payload

    archive_path.write_bytes(b"different archive")
    with pytest.raises(ArtifactValidationError, match="ARCHIVE_HASH_COLLISION"):
        collector_notebook._upload_content_addressed(str(archive_path), payload, digest)
    assert archive_path.read_bytes() == b"different archive"


def test_staged_archive_is_deterministic_and_has_normalized_members(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "attempt"
    _write_staged_artifacts(root)
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))

    first = collector_notebook._staged_archive(_capture_context())
    second = collector_notebook._staged_archive(_capture_context())

    assert first == second
    assert archive_sha256(first) == archive_sha256(second)
    with tarfile.open(fileobj=io.BytesIO(first), mode="r:gz") as archive:
        members = archive.getmembers()
    assert [member.name for member in members] == [
        "target/manifest.json",
        "target/run_results.json",
    ]
    assert all(member.mode == 0o600 for member in members)
    assert all(member.mtime == 0 for member in members)
    assert all(member.uid == member.gid == 0 for member in members)
    assert all(member.uname == member.gname == "" for member in members)


def test_partial_staged_archive_is_quarantined_after_scan_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "attempt"
    _write_staged_artifacts(root, run_results=False)
    context = _capture_context()
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))
    data = collector_notebook._staged_archive(context)

    with pytest.raises(ArtifactValidationError, match="MISSING_REQUIRED_ARTIFACT"):
        scan_archive(data)

    uploaded_paths: list[str] = []
    registry_rows: list[tuple[Any, ...]] = []
    monkeypatch.setattr(collector_notebook, "_staged_archive", lambda _context: data)
    monkeypatch.setattr(collector_notebook, "_existing_hash", lambda *_args: None)
    monkeypatch.setattr(
        collector_notebook,
        "_upload_content_addressed",
        lambda path, _data, _digest: uploaded_paths.append(path),
    )
    monkeypatch.setattr(
        collector_notebook,
        "_upsert_registry",
        lambda _spark, _context, row: registry_rows.append(row),
    )

    with pytest.raises(ArtifactValidationError, match="MISSING_REQUIRED_ARTIFACT"):
        collector_notebook._capture_one(None, context)

    assert len(uploaded_paths) == 1
    assert "/quarantine/" in uploaded_paths[0]
    assert [(row[8], row[9]) for row in registry_rows] == [
        ("QUARANTINED", "MISSING_REQUIRED_ARTIFACT")
    ]


def test_staged_archive_reports_not_produced_when_no_expected_files_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty-attempt"
    root.mkdir()
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))

    with pytest.raises(ArtifactValidationError) as exc_info:
        collector_notebook._staged_archive(_capture_context())

    assert exc_info.value.code == "STAGED_ARTIFACT_NOT_PRODUCED"


def test_staged_archive_rejects_symlink_attempt_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    _write_staged_artifacts(outside)
    root = tmp_path / "attempt"
    root.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))

    with pytest.raises(ArtifactValidationError, match="STAGED_ARTIFACT_TYPE_INVALID"):
        collector_notebook._staged_archive(_capture_context())

    assert (outside / "target" / "manifest.json").exists()


def test_numeric_staging_directories_accept_zero_for_repair_and_execution(
    tmp_path: Path,
) -> None:
    repair = tmp_path / "repair_count=0"
    repair.mkdir()
    execution = repair / "execution_count=0"
    execution.mkdir()

    assert collector_notebook._numeric_staging_directories(str(tmp_path), "repair_count") == [
        (0, str(repair))
    ]
    assert collector_notebook._numeric_staging_directories(str(repair), "execution_count") == [
        (0, str(execution))
    ]


def test_numeric_staging_directories_reject_symlink_parent(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = tmp_path / "parent"
    parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ArtifactValidationError, match="STAGING_DIRECTORY_TYPE_INVALID"):
        collector_notebook._numeric_staging_directories(str(parent), "repair_count")


def test_numeric_staging_directories_bounds_unexpected_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "unexpected-one").mkdir()
    (tmp_path / "unexpected-two").mkdir()
    monkeypatch.setattr(collector_notebook, "_MAX_STAGING_ENTRIES", 1)

    with pytest.raises(ArtifactValidationError, match="STAGING_DIRECTORY_LIMIT_EXCEEDED"):
        collector_notebook._numeric_staging_directories(str(tmp_path), "repair_count")


class _ListRunsJobs:
    def __init__(self, runs: list[SimpleNamespace]) -> None:
        self.runs = runs
        self.kwargs: dict[str, Any] = {}

    def list_runs(self, **kwargs: Any) -> list[SimpleNamespace]:
        self.kwargs = kwargs
        return self.runs

    def get_run(self, **_kwargs: Any) -> SimpleNamespace:
        raise AssertionError("authorized staged task runs must not require a detail lookup")


def _task(
    run_id: int,
    *,
    job_run_id: int,
    attempt_number: int = 0,
    result_state: str | None = "SUCCESS",
    termination_code: str | None = None,
    instrumented: bool = True,
    templated: bool = False,
) -> SimpleNamespace:
    state = (
        None
        if result_state is None
        else SimpleNamespace(result_state=SimpleNamespace(value=result_state))
    )
    status = SimpleNamespace(termination_details=SimpleNamespace(code=termination_code))
    command = "dbt build"
    if instrumented:
        if templated:
            staging_root = (
                "/Volumes/catalog/schema/staging/workspace_id={{workspace.id}}/"
                "job_id={{job.id}}/job_run_id={{job.run_id}}/"
                "repair_count={{job.repair_count}}/task_run_id={{task.run_id}}/"
                "execution_count={{task.execution_count}}"
            )
        else:
            staging_root = (
                "/Volumes/catalog/schema/staging/workspace_id=1/job_id=2/"
                f"job_run_id={job_run_id}/repair_count=0/task_run_id={run_id}/"
                "execution_count=0"
            )
        command = f'dbt build --target-path "{staging_root}/target"'
    return SimpleNamespace(
        task_key="dbt_nyc_taxi",
        run_id=run_id,
        attempt_number=attempt_number,
        dbt_task=SimpleNamespace(commands=[command]),
        state=state,
        status=status,
    )


def test_capture_discovery_returns_full_context_and_independent_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = "/Volumes/catalog/schema/staging/workspace_id=1/job_id=2/job_run_id=100"
    repair_path = f"{run_root}/repair_count=0"
    task_path = f"{repair_path}/task_run_id=11"
    partial_task_path = f"{repair_path}/task_run_id=13"
    directory_results = {
        (run_root, "repair_count"): [(0, repair_path)],
        (repair_path, "task_run_id"): [
            (11, task_path),
            (13, partial_task_path),
        ],
        (task_path, "execution_count"): [(0, f"{task_path}/execution_count=0")],
    }
    monkeypatch.setattr(
        collector_notebook,
        "_numeric_staging_directories",
        lambda path, key: directory_results.get((path, key), []),
    )
    jobs = _ListRunsJobs(
        [
            SimpleNamespace(
                job_id=2,
                run_id=100,
                start_time=1_000,
                tasks=[
                    _task(11, job_run_id=100),
                    _task(
                        12,
                        job_run_id=100,
                        result_state=None,
                        termination_code="RUN_EXECUTION_ERROR",
                        templated=True,
                    ),
                    _task(13, job_run_id=100),
                ],
                repair_history=[],
            )
        ]
    )

    discovery = collector_notebook._completed_capture_contexts(
        cast(Any, SimpleNamespace(jobs=jobs)),
        _collector_config(),
    )

    assert discovery == collector_notebook.CaptureDiscovery(
        contexts=(
            collector_notebook.CaptureContext(
                workspace_id=1,
                job_id=2,
                job_run_id=100,
                task_run_id=11,
                repair_count=0,
                execution_count=0,
                task_key="dbt_nyc_taxi",
                upstream_result_state="success",
                catalog="catalog",
                schema="schema",
                volume="volume",
                staging_volume="staging",
            ),
        ),
        gaps=(
            collector_notebook.CaptureContext(
                workspace_id=1,
                job_id=2,
                job_run_id=100,
                task_run_id=12,
                repair_count=0,
                execution_count=1,
                task_key="dbt_nyc_taxi",
                upstream_result_state="failed",
                catalog="catalog",
                schema="schema",
                volume="volume",
                staging_volume="staging",
            ),
            collector_notebook.CaptureContext(
                workspace_id=1,
                job_id=2,
                job_run_id=100,
                task_run_id=13,
                repair_count=0,
                execution_count=1,
                task_key="dbt_nyc_taxi",
                upstream_result_state="success",
                catalog="catalog",
                schema="schema",
                volume="volume",
                staging_volume="staging",
            ),
        ),
    )
    assert jobs.kwargs["job_id"] == 2
    assert jobs.kwargs["completed_only"] is True
    assert jobs.kwargs["expand_tasks"] is True


def test_discovery_gap_maps_original_retry_and_repair_attempt_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        collector_notebook,
        "_numeric_staging_directories",
        lambda *_args: [],
    )
    tasks = [
        _task(
            30,
            job_run_id=300,
            attempt_number=0,
            result_state=None,
            termination_code="RUN_EXECUTION_ERROR",
            templated=True,
        ),
        _task(
            31,
            job_run_id=300,
            attempt_number=1,
            result_state=None,
            termination_code="RUN_EXECUTION_ERROR",
            templated=True,
        ),
        _task(
            32,
            job_run_id=300,
            attempt_number=2,
            templated=True,
        ),
    ]
    jobs = _ListRunsJobs(
        [
            SimpleNamespace(
                job_id=2,
                run_id=300,
                start_time=3_000,
                tasks=tasks,
                repair_history=[
                    SimpleNamespace(task_run_ids=[30]),
                    SimpleNamespace(task_run_ids=[32]),
                ],
            )
        ]
    )

    discovery = collector_notebook._completed_capture_contexts(
        cast(Any, SimpleNamespace(jobs=jobs)),
        _collector_config(),
    )

    assert [gap.task_run_id for gap in discovery.gaps] == [30, 31, 32]
    assert [gap.repair_count for gap in discovery.gaps] == [0, 0, 1]
    assert [gap.execution_count for gap in discovery.gaps] == [1, 2, 3]
    assert [gap.upstream_result_state for gap in discovery.gaps] == [
        "failed",
        "failed",
        "success",
    ]


def test_discovery_suppresses_post_cleanup_gap_for_terminal_template_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        collector_notebook,
        "_numeric_staging_directories",
        lambda *_args: [],
    )
    task = _task(21, job_run_id=200, templated=True)
    jobs = _ListRunsJobs(
        [
            SimpleNamespace(
                job_id=2,
                run_id=200,
                start_time=2_000,
                tasks=[task],
                repair_history=[],
            )
        ]
    )
    terminal = _capture_context(
        job_run_id=200,
        task_run_id=21,
        execution_count=1,
    ).attempt_key

    discovery = collector_notebook._completed_capture_contexts(
        cast(Any, SimpleNamespace(jobs=jobs)),
        _collector_config(),
        frozenset({terminal}),
    )

    assert discovery == collector_notebook.CaptureDiscovery(contexts=(), gaps=())


def test_capture_marks_registry_complete_only_after_facts_are_merged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _valid_archive()
    events: list[str] = []
    context = _capture_context(repair_count=1, execution_count=2)
    monkeypatch.setattr(collector_notebook, "_staged_archive", lambda _context: data)
    monkeypatch.setattr(collector_notebook, "_existing_hash", lambda *_args: None)
    monkeypatch.setattr(collector_notebook, "_upload_content_addressed", lambda *_args: None)
    monkeypatch.setattr(
        collector_notebook,
        "_upsert_registry",
        lambda _spark, _context, row: events.append(f"registry:{row[8]}"),
    )
    monkeypatch.setattr(
        collector_notebook,
        "_upsert_parsed_facts",
        lambda *_args: events.append("facts"),
    )

    collector_notebook._capture_one(None, context)

    assert events == ["facts", "registry:COMPLETE"]


def test_recursive_cleanup_deletes_nested_staging_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "attempt"
    nested = root / "target" / "compiled" / "models"
    nested.mkdir(parents=True)
    (root / "target" / "manifest.json").write_text("{}")
    (nested / "model.sql").write_text("select 1")
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))

    collector_notebook._delete_staging(_capture_context())

    assert not root.exists()


def test_recursive_cleanup_rejects_symlinks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "attempt"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("must survive")
    (root / "link").symlink_to(outside)
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))

    with pytest.raises(ArtifactValidationError, match="STAGING_CLEANUP_TYPE_INVALID"):
        collector_notebook._delete_staging(_capture_context())

    assert outside.read_text() == "must survive"
    assert root.exists()


def test_recursive_cleanup_rejects_symlink_attempt_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "must-survive.txt"
    protected.write_text("must survive")
    root = tmp_path / "attempt"
    root.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))

    with pytest.raises(ArtifactValidationError, match="STAGING_CLEANUP_TYPE_INVALID"):
        collector_notebook._delete_staging(_capture_context())

    assert protected.read_text() == "must survive"
    assert root.is_symlink()


def test_recursive_cleanup_enforces_depth_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "attempt"
    (root / "one" / "two").mkdir(parents=True)
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))
    monkeypatch.setattr(collector_notebook, "_MAX_STAGING_DEPTH", 1)

    with pytest.raises(ArtifactValidationError, match="STAGING_CLEANUP_DEPTH_EXCEEDED"):
        collector_notebook._delete_staging(_capture_context())

    assert root.exists()


def test_recursive_cleanup_enforces_entry_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "attempt"
    root.mkdir()
    (root / "one").write_text("1")
    (root / "two").write_text("2")
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(root))
    monkeypatch.setattr(collector_notebook, "_MAX_STAGING_ENTRIES", 1)

    with pytest.raises(
        ArtifactValidationError,
        match="STAGING_CLEANUP_ENTRY_LIMIT_EXCEEDED",
    ):
        collector_notebook._delete_staging(_capture_context())

    assert sorted(path.name for path in root.iterdir()) == ["one", "two"]


def test_recursive_cleanup_missing_root_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "already-deleted"
    monkeypatch.setattr(collector_notebook, "_staging_root", lambda _context: str(missing))

    collector_notebook._delete_staging(_capture_context())

    assert not missing.exists()


def test_registry_row_matches_schema_order_and_cleanup_fields() -> None:
    data = _valid_archive()
    scan = scan_archive(data)
    parsed = parse_artifacts(scan)
    captured_at = parsed.generated_at.replace(tzinfo=None)
    digest = archive_sha256(data)
    row = collector_notebook._registry_row(
        _capture_context(repair_count=1, execution_count=2),
        captured_at=captured_at,
        capture_status="COMPLETE",
        capture_error_code=None,
        path="/Volumes/catalog/schema/volume/raw/archive.tar.gz",
        digest=digest,
        archive_bytes=len(data),
        scan=scan,
        parsed=parsed,
    )
    columns = [
        definition.strip().split()[0]
        for definition in collector_notebook._REGISTRY_SCHEMA.strip().split(",")
    ]
    expected_columns = [
        "workspace_id",
        "job_id",
        "job_run_id",
        "repair_count",
        "task_run_id",
        "execution_count",
        "task_key",
        "upstream_result_state",
        "capture_status",
        "capture_error_code",
        "captured_at",
        "staging_cleanup_status",
        "staging_cleanup_error_code",
        "staging_cleanup_updated_at",
        "staging_deleted_at",
        "archive_path",
        "archive_sha256",
        "archive_bytes",
        "file_count",
        "total_uncompressed_bytes",
        "invocation_id",
        "dbt_version",
        "adapter_type",
        "manifest_schema_version",
        "run_results_schema_version",
        "parser_version",
    ]

    assert columns == expected_columns
    assert len(row) == len(columns) == 26
    values = dict(zip(columns, row, strict=True))
    assert values["repair_count"] == 1
    assert values["execution_count"] == 2
    assert values["capture_status"] == "COMPLETE"
    assert values["staging_cleanup_status"] == "PENDING"
    assert values["staging_cleanup_error_code"] is None
    assert values["staging_cleanup_updated_at"] == captured_at
    assert values["staging_deleted_at"] is None
    assert values["archive_sha256"] == digest


def _patch_main_runtime(
    monkeypatch: pytest.MonkeyPatch,
    config: collector_notebook.CollectorConfig,
) -> None:
    fake_client = SimpleNamespace(get_workspace_id=lambda: 1)
    monkeypatch.setattr(collector_notebook, "WorkspaceClient", lambda: fake_client)
    monkeypatch.setattr(
        collector_notebook.CollectorConfig,
        "from_widgets",
        classmethod(lambda _cls, *, workspace_id: config),
    )
    monkeypatch.setattr(collector_notebook, "_spark_session", lambda: object())
    monkeypatch.setattr(collector_notebook, "_ensure_delta_objects", lambda *_args: None)
    monkeypatch.setattr(collector_notebook, "_create_curated_views", lambda *_args: None)


def test_main_reconciles_cleanup_without_recapturing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _collector_config()
    context = _capture_context(job_run_id=30, task_run_id=40)
    _patch_main_runtime(monkeypatch, config)
    monkeypatch.setattr(
        collector_notebook,
        "_completed_capture_contexts",
        lambda *_args: collector_notebook.CaptureDiscovery(contexts=(), gaps=()),
    )
    states = iter(
        [
            collector_notebook.RegistryCaptureState(
                terminal_attempts=frozenset(),
                last_attempted_at={},
                cleanup_pending=(),
            ),
            collector_notebook.RegistryCaptureState(
                terminal_attempts=frozenset({context.attempt_key}),
                last_attempted_at={context.attempt_key: 100.0},
                cleanup_pending=(context,),
            ),
        ]
    )
    monkeypatch.setattr(
        collector_notebook,
        "_registry_capture_state",
        lambda *_args: next(states),
    )
    monkeypatch.setattr(
        collector_notebook,
        "_capture_one",
        lambda *_args: pytest.fail("cleanup reconciliation must not recapture"),
    )
    events: list[tuple[str, object, object]] = []
    monkeypatch.setattr(
        collector_notebook,
        "_delete_staging",
        lambda captured_context: events.append(("delete", captured_context, None)),
    )
    monkeypatch.setattr(
        collector_notebook,
        "_record_staging_cleanup",
        lambda _spark, captured_context, *, deleted, error_code: events.append(
            ("record", captured_context, (deleted, error_code))
        ),
    )

    collector_notebook.main()

    assert events == [
        ("delete", context, None),
        ("record", context, (True, None)),
    ]


def test_main_persists_discovery_gap_as_not_produced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _collector_config()
    gap = _capture_context(
        job_run_id=31,
        task_run_id=41,
        repair_count=0,
        execution_count=2,
        upstream_result_state="failed",
    )
    _patch_main_runtime(monkeypatch, config)
    monkeypatch.setattr(
        collector_notebook,
        "_completed_capture_contexts",
        lambda *_args: collector_notebook.CaptureDiscovery(contexts=(), gaps=(gap,)),
    )
    states = iter(
        [
            collector_notebook.RegistryCaptureState(
                terminal_attempts=frozenset(),
                last_attempted_at={},
                cleanup_pending=(),
            ),
            collector_notebook.RegistryCaptureState(
                terminal_attempts=frozenset({gap.attempt_key}),
                last_attempted_at={gap.attempt_key: 100.0},
                cleanup_pending=(gap,),
            ),
        ]
    )
    monkeypatch.setattr(
        collector_notebook,
        "_registry_capture_state",
        lambda *_args: next(states),
    )
    registry_rows: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        collector_notebook,
        "_upsert_registry",
        lambda _spark, _context, row: registry_rows.append(row),
    )
    monkeypatch.setattr(collector_notebook, "_delete_staging", lambda _context: None)
    monkeypatch.setattr(
        collector_notebook,
        "_record_staging_cleanup",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(RuntimeError, match="incomplete for 1 task run"):
        collector_notebook.main()

    assert len(registry_rows) == 1
    columns = [field.strip().split()[0] for field in collector_notebook._REGISTRY_SCHEMA.split(",")]
    values = dict(zip(columns, registry_rows[0], strict=True))
    assert values["repair_count"] == 0
    assert values["execution_count"] == 2
    assert values["capture_status"] == "NOT_PRODUCED"
    assert values["capture_error_code"] == "STAGED_ARTIFACT_NOT_PRODUCED"


def test_main_bounds_discovery_gaps_with_capture_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(_collector_config(), max_task_runs_per_sweep=1)
    gaps = (
        _capture_context(job_run_id=31, task_run_id=41),
        _capture_context(job_run_id=32, task_run_id=42),
    )
    _patch_main_runtime(monkeypatch, config)
    monkeypatch.setattr(
        collector_notebook,
        "_completed_capture_contexts",
        lambda *_args: collector_notebook.CaptureDiscovery(contexts=(), gaps=gaps),
    )
    states = iter(
        [
            collector_notebook.RegistryCaptureState(
                terminal_attempts=frozenset(),
                last_attempted_at={},
                cleanup_pending=(),
            ),
            collector_notebook.RegistryCaptureState(
                terminal_attempts=frozenset({gaps[0].attempt_key}),
                last_attempted_at={gaps[0].attempt_key: 100.0},
                cleanup_pending=(gaps[0],),
            ),
        ]
    )
    monkeypatch.setattr(
        collector_notebook,
        "_registry_capture_state",
        lambda *_args: next(states),
    )
    registry_rows: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        collector_notebook,
        "_upsert_registry",
        lambda _spark, _context, row: registry_rows.append(row),
    )
    monkeypatch.setattr(collector_notebook, "_delete_staging", lambda _context: None)
    monkeypatch.setattr(
        collector_notebook,
        "_record_staging_cleanup",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(
        RuntimeError,
        match=r"incomplete for 2 task run\(s\); .*BATCH_DEFERRED",
    ):
        collector_notebook.main()

    assert len(registry_rows) == 1


def test_main_preserves_discovery_error_code_in_task_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _collector_config()
    _patch_main_runtime(monkeypatch, config)
    monkeypatch.setattr(
        collector_notebook,
        "_completed_capture_contexts",
        lambda *_args: (_ for _ in ()).throw(
            collector_notebook.ArtifactValidationError("STAGING_LIST_ERROR")
        ),
    )
    monkeypatch.setattr(
        collector_notebook,
        "_registry_capture_state",
        lambda *_args: collector_notebook.RegistryCaptureState(
            terminal_attempts=frozenset(),
            last_attempted_at={},
            cleanup_pending=(),
        ),
    )

    with pytest.raises(RuntimeError, match="error_code=STAGING_LIST_ERROR"):
        collector_notebook.main()


def test_main_batches_unseen_then_oldest_retry_and_reports_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(_collector_config(), max_task_runs_per_sweep=2)
    contexts = [
        _capture_context(
            job_run_id=run_id,
            task_run_id=run_id,
            repair_count=1,
            execution_count=1,
        )
        for run_id in (11, 12, 13)
    ]
    _patch_main_runtime(monkeypatch, config)
    monkeypatch.setattr(
        collector_notebook,
        "_completed_capture_contexts",
        lambda *_args: collector_notebook.CaptureDiscovery(
            contexts=tuple(contexts),
            gaps=(),
        ),
    )
    registry_state = collector_notebook.RegistryCaptureState(
        terminal_attempts=frozenset(),
        last_attempted_at={
            contexts[0].attempt_key: 200.0,
            contexts[1].attempt_key: 100.0,
        },
        cleanup_pending=(),
    )
    monkeypatch.setattr(
        collector_notebook,
        "_registry_capture_state",
        lambda *_args: registry_state,
    )
    captured: list[int] = []
    monkeypatch.setattr(
        collector_notebook,
        "_capture_one",
        lambda _spark, context: (
            captured.append(context.task_run_id) or SimpleNamespace(total_nodes=1)
        ),
    )

    with pytest.raises(RuntimeError, match="incomplete for 1 task run"):
        collector_notebook.main()

    # Never-seen task 13 goes first; retry 12 was attempted less recently than 11.
    assert captured == [13, 12]
