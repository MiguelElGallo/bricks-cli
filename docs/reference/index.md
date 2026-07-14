---
icon: lucide/book-open
---

# Reference

The facts, organized for lookup. These pages describe exactly what's in the repo
— commands, fields, values, and layout — without tutorial narration.

<div class="grid cards" markdown>

-   :lucide-terminal: **[CLI commands](cli-commands.md)**

    ---

    The `databricks bundle` subcommands and dbt commands this project uses, plus
    handy global flags.

-   :lucide-file-cog: **[Bundle configuration](bundle-config.md)**

    ---

    Every field in `databricks.yml`: `bundle`, `include`, `variables`, and the
    `dev` / `prod` targets.

-   :lucide-briefcase: **[The dbt job resources](job-resource.md)**

    ---

    The independent dbt source and collector jobs, native health controls,
    tables, and views.

-   :lucide-sliders-horizontal: **[Configuration values](configuration-values.md)**

    ---

    The complete contract of bundle variables, `BUNDLE_VAR_*`, GitHub Variables,
    and `DBT_*` environment variables.

-   :lucide-folder-tree: **[Project layout](project-layout.md)**

    ---

    What every file and directory is for, including the dbt agent skills.

</div>
