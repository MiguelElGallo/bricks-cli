import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/deploy.yml"


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_production_metadata_is_passed_only_to_first_party_steps() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = _workflow()

    assert "${{ vars.DATABRICKS" not in workflow_text
    assert "$GITHUB_ENV" not in workflow_text
    assert workflow["env"] == {"DATABRICKS_AUTH_TYPE": "oauth-m2m"}

    for job_name in ("freeze", "deploy"):
        job = workflow["jobs"][job_name]
        steps = job["steps"]
        assert "env" not in job
        assert all(
            "secrets.DATABRICKS_" not in json.dumps(step) for step in steps if "uses" in step
        )
        for step in steps:
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False
        first_secret_index = next(
            index
            for index, step in enumerate(steps)
            if any("${{ secrets.DATABRICKS_" in value for value in step.get("env", {}).values())
        )

        assert all("uses" in step for step in steps[:first_secret_index])
        assert all("uses" not in step for step in steps[first_secret_index:])

        for step in steps[first_secret_index:]:
            for value in step.get("env", {}).values():
                if value.startswith("${{ secrets."):
                    assert value.startswith("${{ secrets.DATABRICKS_")

    deploy_steps = workflow["jobs"]["deploy"]["steps"]
    cleanup = deploy_steps[-1]
    assert cleanup["name"] == "Remove protected local configuration"
    assert cleanup["if"] == "${{ always() }}"
    assert cleanup["run"] == "rm -rf .databricks/bundle/prod"


def test_public_acceptance_log_omits_databricks_identifiers() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "ACCEPTANCE_RUN_IDS" not in workflow_text
    assert "Source parent run" not in workflow_text
    assert "Source task run" not in workflow_text
    assert "Collector sweep 1: `" not in workflow_text
    assert "Collector sweep 2: `" not in workflow_text
    assert 'echo "::add-mask::$source_job_id"' in workflow_text
    assert 'echo "::add-mask::$collector_job_id"' in workflow_text
    assert 'value="${value//%/%25}"' in workflow_text
    assert 'mask_value "$notification_emails"' in workflow_text
    assert 'mask_value "$recipient"' in workflow_text


def test_notification_masks_escape_workflow_command_percent(
    tmp_path: Path,
) -> None:
    workflow = _workflow()
    configure_step = next(
        step
        for step in workflow["jobs"]["deploy"]["steps"]
        if step.get("name") == "Configure approved notification recipients"
    )
    recipient = "ops%25archive@example.invalid"

    result = subprocess.run(
        ["bash"],
        input=configure_step["run"],
        cwd=tmp_path,
        env={
            **os.environ,
            "DATABRICKS_NOTIFICATION_EMAILS": json.dumps([recipient]),
        },
        check=True,
        capture_output=True,
        text=True,
    )

    assert "::add-mask::ops%2525archive@example.invalid" in result.stdout
    override = json.loads(
        (tmp_path / ".databricks/bundle/prod/variable-overrides.json").read_text(encoding="utf-8")
    )
    assert override == {"notification_emails": [recipient]}
