---
icon: lucide/wrench
---

# How-to guides

Use these guides when you already know the result you need. Each guide owns one
operational task and links to reference or explanation for background detail.

## Develop dbt

- [Run dbt locally](run-dbt-locally.md)
- [Add a dbt model](add-a-model.md)
- [Change the deployed selection](change-the-deployed-selection.md)

## Provision and deploy

- [Set up protected OAuth M2M deployment](set-up-m2m-cicd.md)
- [Grant production prerequisites](grant-production-prerequisites.md)
- [Deploy to production](deploy-to-production.md)
- [Verify a production deployment](verify-production-deployment.md)

## Maintain production access

- [Rotate the deployer secret](rotate-the-deployer-secret.md)
- [Repair production runtime file access](grant-production-runtime-access.md)
- [Rotate runtime identities](rotate-runtime-identities.md)

## Monitor

- [Observability operations](observe-dbt-jobs.md)
- [Configure native alerts](configure-native-alerts.md)
- [Query job health](query-job-health.md)
- [Grant operator access](grant-operator-access.md)

## Recover and manage the evidence lifecycle

- [Investigate a source failure](investigate-a-source-failure.md)
- [Investigate a collector failure](investigate-a-collector-failure.md)
- [Verify missing-artifact capture](verify-failure-capture.md)
- [Clean up a development deployment](clean-up-development.md)
- [Decommission the production deployment and evidence](decommission-production-evidence.md)

!!! info "Availability"

    The live example uses AWS Databricks Free Edition for functional validation.
    Its lack of compliance enforcement, private networking, SLA, and
    account-level APIs means the production guides describe an architecture and
    operating contract—not an assertion that the personal workspace satisfies a
    regulated production control framework.
