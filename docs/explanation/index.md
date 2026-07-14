---
icon: lucide/lightbulb
---

# Explanation

These pages describe why the project is built this way. Use a
[how-to guide](../how-to/index.md) when you already have a task to complete, and
use the [reference](../reference/index.md) when you need exact fields or
commands.

<div class="grid cards" markdown>

-   :lucide-package: **[Why Declarative Automation Bundles](why-asset-bundles.md)**

    ---

    What the bundle deploys, what remains an administrator prerequisite, and why
    deployment includes an ACL reconciliation step.

-   :lucide-key-round: **[The authentication model](authentication.md)**

    ---

    Why humans use OAuth U2M, GitHub uses OAuth M2M, and OIDC is unavailable on
    this Free Edition account.

-   :lucide-cable: **[How dbt connects to Databricks](how-dbt-connects.md)**

    ---

    How local dbt, the deployed source job, and the collector receive different
    credentials and permissions.

-   :lucide-git-compare-arrows: **[Development and production are different controls](development-vs-production.md)**

    ---

    What bundle modes isolate, what they do not isolate, and why a production
    target does not make Free Edition production-ready.

-   :lucide-activity: **[Why observability stays inside Databricks](native-observability.md)**

    ---

    How Jobs state, dbt artifacts, Unity Catalog facts, and optional system
    tables complement one another.

-   :lucide-archive: **[The evidence lifecycle](evidence-lifecycle.md)**

    ---

    How staged artifacts become deterministic evidence, how terminal states and
    cleanup differ, and where the producer trust boundary remains.

-   :lucide-lock: **[Security and secret boundaries](security-and-secrets.md)**

    ---

    The three-identity model, protected M2M secret, restricted raw evidence, and
    limits of hashing and managed Volumes.

</div>
