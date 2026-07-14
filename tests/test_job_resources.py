from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _job(path: str, key: str) -> dict[str, Any]:
    document = yaml.safe_load((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
    return document["resources"]["jobs"][key]


def test_collector_does_not_mask_first_failure_with_an_automatic_retry() -> None:
    job = _job(
        "resources/dbt_observability_collector.job.yml",
        "dbt_observability_collector_job",
    )
    task = job["tasks"][0]

    assert task["max_retries"] == 0
    assert job["email_notifications"]["on_failure"] == "${var.notification_emails}"


def test_source_notifies_only_after_its_final_attempt() -> None:
    job = _job("resources/nyc_taxi.job.yml", "nyc_taxi_dbt_job")
    task = job["tasks"][0]

    assert task["max_retries"] == 1
    assert task["notification_settings"]["alert_on_last_attempt"] is True
