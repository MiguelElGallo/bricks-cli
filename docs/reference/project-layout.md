---
icon: lucide/folder-tree
---

# Project layout

What every file and directory is for.

```text
.
├── databricks.yml                  # bundle definition + dev/prod targets
├── resources/
│   ├── nyc_taxi.job.yml             # source dbt job
│   ├── dbt_observability_collector.job.yml # scheduled collector job
│   └── observability.infrastructure.yml # UC schema + staging/evidence Volumes
├── dbt_project.yml                 # dbt project (paths under src/)
├── dbt_profiles/
│   └── profiles.yml                # dbt profile for local runs (env-var based)
├── profile_template.yml            # prompts for `dbt init` (local profile)
├── requirements-dev.txt            # exact dbt, SDK, test, lint, and type pins
├── pyproject.toml                  # pytest, Ruff, and ty configuration
├── requirements-docs.txt           # Zensical (builds this docs site)
├── zensical.toml                   # documentation site configuration
├── src/
│   ├── seeds/nyc_taxi/             # the seed CSV + its properties
│   ├── models/nyc_taxi/           # the single table model + tests
│   ├── observability/              # artifact collector + pure parser helpers
│   └── analyses/, macros/, snapshots/, tests/   # standard dbt folders (empty)
├── tests/                          # isolated artifact parser/security tests
├── docs/                           # this documentation site (Markdown sources)
├── .github/workflows/             # CI (validate), deploy (OIDC), docs (Pages)
└── .agents/skills/                # installed dbt agent skills
```

## Key files

| Path | Role |
|------|------|
| `databricks.yml` | Bundle root — see [Bundle configuration](bundle-config.md) |
| `resources/nyc_taxi.job.yml` | Source dbt job — see [The dbt job resources](job-resource.md) |
| `resources/dbt_observability_collector.job.yml` | Independent 15-minute collector job |
| `resources/observability.infrastructure.yml` | Target-scoped observability schema plus staging and evidence managed Volumes |
| `dbt_project.yml` | dbt paths and seed/model config |
| `dbt_profiles/profiles.yml` | Local-only dbt connection, fully env-var based |
| `pyproject.toml` | pytest discovery plus Ruff and ty settings |
| `src/seeds/nyc_taxi/nyc_taxi_trips_seed.csv` | 100-row seed from `samples.nyctaxi.trips` |
| `src/models/nyc_taxi/nyc_taxi_trips.sql` | The one table model |
| `src/observability/collect_dbt_artifacts.py` | Serverless collector notebook |
| `src/observability/collector_core.py` | Pure archive validation and normalization helpers |
| `tests/test_collector_core.py` | Offline security, schema, sanitization, and idempotency tests |
| `.github/workflows/ci.yml` | PR validation (dev) via OIDC |
| `.github/workflows/deploy.yml` | Deploy + run (prod) via OIDC |
| `.github/workflows/docs.yml` | Build & publish this site to GitHub Pages |

## What's git-ignored

These local state files — which can carry workspace values — are git-ignored:

```text
.databricks/            # bundle state (host, user) — local only
.venv/  target/  logs/  dbt_packages/
.databrickscfg  *.local.yml  **/variable-overrides*.json  .env.local
/site/  docs/_build/    # built documentation output
```

## dbt agent skills

The official
[dbt-labs/dbt-agent-skills](https://github.com/dbt-labs/dbt-agent-skills) are
installed under `.agents/skills/` (via the Vercel `skills` CLI):

```bash
npx skills add dbt-labs/dbt-agent-skills/skills/dbt \
  --agent github-copilot --skill '*' -y --copy
```

These are [Agent Skills](https://agentskills.io/) — folders of instructions an AI
agent loads automatically when your request matches (for example,
`using-dbt-for-analytics-engineering`, `running-dbt-commands`,
`adding-dbt-unit-test`). They make an agent more accurate at writing and running
dbt for the **dbt-databricks** adapter used here. `skills-lock.json` records the
installed set.
