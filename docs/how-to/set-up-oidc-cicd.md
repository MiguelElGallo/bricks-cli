---
icon: lucide/link-2-off
---

# GitHub OIDC setup moved

This page preserves a formerly published URL. GitHub workload identity
federation is not configurable on the tested Databricks Free Edition account:
the feature requires an account-level federation policy, while Free Edition has
no account console or account-level APIs.

Use [Set up OAuth M2M CI/CD](set-up-m2m-cicd.md) for this repository's tested
deployment path. Use [Authentication support](../reference/authentication-support.md)
to understand when `github-oidc` becomes available after moving to an eligible
Databricks account.

Do not copy the previous OIDC procedure into this personal workspace; it cannot
create the required trust policy.
