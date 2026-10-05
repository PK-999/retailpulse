# RetailPulse documentation

Start with [project status](project-status.md) for current verification and prioritized portfolio
improvements. This directory is the project’s reference set:

1. [Requirements](requirements.md) — scope, acceptance criteria, and traceability.
2. [Architecture](architecture.md) — system boundaries, flows, storage layers, and decisions.
3. [Key features](key-features.md) — implemented capabilities and where their code lives.
4. [Project status](project-status.md) — what is verified, what is only prepared, and what remains.
5. [Execution plan](execution-plan.md) — staged path from local verification to the Azure demo.
6. [Cost strategy](cost-strategy.md) — local-first profiles and paid-compute guardrails.
7. [Event contract](data-contract.md) — version 1 event fields and topic routing.
8. [Demo guide](demo-guide.md) — repeatable healthy and failure demonstrations.
9. [Runbooks](runbooks/) — operator response procedures.
10. [Verification evidence](evidence/) — stage results, run identifiers, and saved reports.
11. [Decision records](decisions/) — reviewed deployment, identity, cost, and teardown choices.
12. [Security access matrix](security/access-matrix.md) — Azure identities, roles, and scopes.
13. [Portfolio walkthrough](portfolio-walkthrough.md) — recorded demo, chapters, and reproduction.

The accepted BI delivery choice is recorded in
[the RetailPulse BI Lite decision](decisions/bi-dashboard.md).

For this release, start with the [completion checklist](release-checklist.md),
[aggregate local proof](evidence/local-e2e.json), and
[cloud monitoring preflight](evidence/cloud-monitor-preflight.json).

## Document ownership

The requirements matrix is the source of truth for scope. A feature should not be described as
complete unless its acceptance criteria pass and the project-status document records the level
at which it was verified.

When changing the platform:

1. Update the requirement or add a new requirement ID.
2. Update the architecture if the data flow, trust boundary, or storage contract changes.
3. Add or update automated tests.
4. Update project status with the new evidence and validation date.
5. Update the demo guide if an operator-facing command changes.
