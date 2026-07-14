---
icon: lucide/book-a
---

# Glossary

Repository-specific terms are defined here with the meaning used by executable
configuration and collector code.

| Term | Definition |
|------|------------|
| **Application ID** | UUID-like service-principal client ID used by OAuth and bundle `service_principal_name` fields; different from a Databricks numeric service-principal ID |
| **AttemptKey** | Six-field identity `(workspace_id, job_id, job_run_id, repair_count, task_run_id, execution_count)` |
| **Bundle resource key** | Stable YAML key such as `nyc_taxi_dbt_job`; it can differ from the deployed display name |
| **Canonical archive** | Deterministic gzip tar retained below `raw/` after validation and identified by SHA-256 |
| **Capture** | Staging read, deterministic packaging, validation, persistence, fact merge, and registry reconciliation |
| **Cleanup** | Independent deletion of a terminal attempt's staging root |
| **Collector** | Independent Lakeflow job that discovers completed source attempts and creates governed evidence |
| **Declarative Automation Bundle** | Databricks CLI project-as-code unit historically called an Asset Bundle |
| **Evidence Volume** | Collector-only managed Unity Catalog Volume containing raw and quarantine archives |
| **Execution count** | Attempt execution dimension supplied by Lakeflow dynamic values; distinct from task run ID |
| **Free Edition** | No-cost, non-commercial Databricks account tier with serverless and administrative limitations |
| **Guaranteed view** | `dbt_run_health` or `dbt_node_health`, refreshed independently of system-table access |
| **Lakeflow Jobs** | Databricks job orchestration service used for both source and collector jobs |
| **OAuth M2M** | Service-principal client credential authentication used by protected production GitHub deployment |
| **OAuth U2M** | Browser-based user authentication recommended for local CLI use |
| **Optional view** | Lakeflow system-table-backed view created on a best-effort basis |
| **Quarantine** | Content-addressed storage zone for packaged bytes rejected by the allowlisted parser |
| **Repair count** | Dimension separating original and repaired job executions |
| **Run as** | Workspace identity under which a Lakeflow job executes, distinct from its deployer |
| **Sanitized facts** | Explicitly allowlisted operational fields that exclude raw logs, free-form messages, compiled SQL, and full adapter responses |
| **Source job** | Lakeflow job whose single task runs dbt and stages JSON artifacts |
| **Staging Volume** | Managed Unity Catalog Volume containing short-lived per-attempt dbt target output |
| **Target** | Context-dependent term: bundle target (`dev`/`prod`), dbt profile target, or dbt `--target-path`; these are separate contracts |
| **Terminal capture** | `COMPLETE`, hash-backed `QUARANTINED`, or `NOT_PRODUCED`; scheduled sweeps do not recapture it |
| **WORM** | Write once, read many retention; a managed Unity Catalog Volume is not WORM storage |

