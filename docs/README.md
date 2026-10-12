# Documentation

Start with the [demo guide](demo-guide.md). Then read the [architecture](architecture.md)
and [project status](project-status.md) to understand the implementation and its verification scope.

## For a portfolio reviewer

| Document | Purpose |
|---|---|
| [Demo guide](demo-guide.md) | Reproduce and present the complete local flow |
| [Architecture](architecture.md) | Execution paths, component responsibilities, invariants, tradeoffs |
| [Project status](project-status.md) | Readiness, evidence, and remaining limits |
| [Walkthrough](portfolio-walkthrough.md) | Recorded tour, chapters, and media verification |
| [Evidence index](evidence/README.md) | Dated local proofs and historical Azure results |

## Implementation reference

- [Event contract](data-contract.md): schema, topics, required fields, and validation.
- [Requirements](requirements.md): acceptance criteria and traceability.
- [Duplicate events](runbooks/duplicate-events.md), [malformed events](runbooks/malformed-events.md),
  [pipeline failure](runbooks/pipeline-failure.md): operator response procedures.

## Optional Azure integration

- [Execution plan](execution-plan.md): prerequisites and stage runbooks, with fresh cloud gates deferred.
- [Cost strategy](cost-strategy.md): bounded execution and historical cost assumptions.
- [Deployment decision](decisions/azure-deployment.md), [BI decision](decisions/bi-dashboard.md),
  [access matrix](security/access-matrix.md): identities, storage, publication, and cost boundaries.

Maintain the current demo guide and status when changing behavior. Save dated, non-secret evidence
for verification claims. Historical cloud results do not certify the current deployment.
