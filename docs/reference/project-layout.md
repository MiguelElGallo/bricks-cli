---
icon: lucide/folder-tree
---

# Project layout

What every file and directory is for.

```text
.
├── databricks.yml                  # bundle definition + dev/prod targets
├── resources/
│   └── nyc_taxi.job.yml             # serverless job that runs the dbt task
├── dbt_project.yml                 # dbt project (paths under src/)
├── dbt_profiles/
│   └── profiles.yml                # dbt profile for local runs (env-var based)
├── profile_template.yml            # prompts for `dbt init` (local profile)
├── requirements-dev.txt            # dbt-databricks adapter (local dev)
├── requirements-docs.txt           # Zensical (builds this docs site)
├── zensical.toml                   # documentation site configuration
├── src/
│   ├── seeds/nyc_taxi/             # the seed CSV + its properties
│   ├── models/nyc_taxi/           # the single table model + tests
│   ├── analyses/ macros/ snapshots/ tests/   # standard dbt folders (empty)
├── docs/                           # this documentation site (Markdown sources)
├── .github/workflows/             # CI (validate), deploy (OIDC), docs (Pages)
└── .agents/skills/                # installed dbt agent skills
```

## Key files

| Path | Role |
|------|------|
| `databricks.yml` | Bundle root — see [Bundle configuration](bundle-config.md) |
| `resources/nyc_taxi.job.yml` | The dbt job — see [The dbt job resource](job-resource.md) |
| `dbt_project.yml` | dbt paths and seed/model config |
| `dbt_profiles/profiles.yml` | Local-only dbt connection, fully env-var based |
| `src/seeds/nyc_taxi/nyc_taxi_trips_seed.csv` | 100-row seed from `samples.nyctaxi.trips` |
| `src/models/nyc_taxi/nyc_taxi_trips.sql` | The one table model |
| `.github/workflows/ci.yml` | PR validation (dev) via OIDC |
| `.github/workflows/deploy.yml` | Deploy + run (prod) via OIDC |
| `.github/workflows/docs.yml` | Build & publish this site to GitHub Pages |

## What's git-ignored

Local state and any file that could carry a workspace value never enters git:

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
