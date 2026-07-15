---
icon: lucide/folder-tree
---

# Project layout

This repository keeps deployable configuration, dbt sources, observability
code, tests, and documentation in one bundle root.

```text
.
├── databricks.yml
├── resources/
│   ├── nyc_taxi.job.yml
│   ├── dbt_observability_collector.job.yml
│   └── observability.infrastructure.yml
├── dbt_project.yml
├── dbt_profiles/profiles.yml
├── profile_template.yml
├── src/
│   ├── models/nyc_taxi/
│   ├── models/weather/
│   ├── seeds/nyc_taxi/
│   ├── seeds/weather/
│   ├── tests/
│   └── observability/
│       ├── collect_dbt_artifacts.py
│       └── collector_core.py
├── tests/
│   ├── test_collector_core.py
│   └── test_job_resources.py
├── .github/workflows/
│   ├── ci.yml
│   ├── deploy.yml
│   └── docs.yml
├── docs/
├── pyproject.toml
├── requirements-dev.txt
├── requirements-docs.txt
└── zensical.toml
```

## Key files

| Path | Responsibility |
|------|----------------|
| `databricks.yml` | Bundle identity, variables, targets, production identities, grants, and retention guards |
| `resources/nyc_taxi.job.yml` | Source serverless dbt job |
| `resources/dbt_observability_collector.job.yml` | Scheduled collector job and notebook parameters |
| `resources/observability.infrastructure.yml` | Target-scoped schema plus staging and evidence managed Volumes |
| `dbt_project.yml` | dbt project, paths, materialization, typed seed, and anonymous-telemetry setting |
| `dbt_profiles/profiles.yml` | Environment-only local dbt connection targets |
| `src/observability/collector_core.py` | Pure archive validation and allowlisted normalization |
| `src/observability/collect_dbt_artifacts.py` | Deployed notebook adapter, Jobs discovery, Delta persistence, views, and cleanup |
| `tests/test_collector_core.py` | Collector security, state, idempotency, and schema tests |
| `tests/test_job_resources.py` | Bundle/job contract tests |
| `.github/workflows/ci.yml` | Credential-free PR quality, strict docs build, and offline dbt graph validation |
| `.github/workflows/deploy.yml` | Protected OAuth M2M production deployment and two-job smoke test |
| `.github/workflows/docs.yml` | Strict Zensical build and GitHub Pages publication |

## dbt tree

| Path | Resource |
|------|----------|
| `src/seeds/nyc_taxi/nyc_taxi_trips_seed.csv` | Committed 101-row seed |
| `src/seeds/nyc_taxi/properties.yml` | Seed metadata |
| `src/models/nyc_taxi/nyc_taxi_trips.sql` | Taxi Delta-table model |
| `src/models/nyc_taxi/schema.yml` | Model descriptions and two `not_null` tests |
| `src/seeds/weather/weather_daily_seed.csv` | Eight-row synthetic weather seed |
| `src/seeds/weather/properties.yml` | Synthetic-data notice, metadata, and seed tests |
| `src/models/weather/weather_daily_observations.sql` | Station-date weather view |
| `src/models/weather/weather_station_summary.sql` | Station-grain Delta summary table |
| `src/models/weather/schema.yml` | Weather model descriptions and key tests |
| `src/tests/weather_*.sql` | Weather range and reconciliation tests |

See [dbt project](dbt-project.md) for the executable contract.

## Generated and local-only paths

The following are ignored and must not be committed:

| Path | Contents |
|------|----------|
| `.databricks/` | Local bundle state and overrides |
| `.databrickscfg` | Local CLI profiles if created inside the repository |
| `.env*`, `*.local.yml`, `*.local.yaml` | Local values and secrets |
| `target/`, `logs/`, `dbt_packages/` | dbt output and packages |
| `.venv/`, Python/tool caches | Local development environment |
| `site/`, `docs/_build/` | Generated documentation |

`~/.databrickscfg` is outside the repository but should still be treated as
credential-bearing local configuration.

## Agent skills

`.agents/skills/` contains copied dbt agent-skill instructions and
`skills-lock.json` records their installation. They are development aids and
are not uploaded as Lakeflow tasks or imported by the collector runtime.
