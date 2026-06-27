---
icon: lucide/lightbulb
---

# Explanation

Background and design rationale. These pages don't tell you *how* to do a task —
they help you understand *why* the project is built the way it is, so the
[how-to guides](../how-to/index.md) and [reference](../reference/index.md) make
sense.

<div class="grid cards" markdown>

-   :lucide-package: **[Why Declarative Automation Bundles](why-asset-bundles.md)**

    ---

    What a bundle is, and why "direct deployment" (no Terraform) is the answer to
    this repo's central question.

-   :lucide-key-round: **[The authentication model](authentication.md)**

    ---

    How unified auth resolves credentials, and why this repo uses Azure CLI
    locally and OIDC in CI.

-   :lucide-cable: **[How dbt connects to Databricks](how-dbt-connects.md)**

    ---

    The deployed job and local runs connect differently — and why the job's
    commands omit `--target`.

-   :lucide-lock: **[Keeping secrets out of git](security-and-secrets.md)**

    ---

    The layered approach — bundle variables, env vars, GitHub Variables, OIDC,
    `.gitignore` — that keeps every workspace value out of the repo.

</div>
