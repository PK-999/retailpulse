# Readiness and verification

Reviewed **12 October 2026**. RetailPulse is ready as an end-to-end local data engineering
portfolio. The default demo runs without Azure credentials, Docker, or a model server.
The [demo guide](demo-guide.md) is the single reproduction path.

## Current local verification

| Area | Result | Evidence |
|---|---|---|
| Complete flow | 295 Bronze = 266 Silver + 19 duplicates + 10 quarantine; 10 orders, 57 units, £268.55 | [Latest local proof](evidence/local-e2e.json) |
| Analytics | 37 dbt nodes pass each clean/incremental/full-refresh build; unchanged rerun and full-refresh equivalence | [Local proof](evidence/local-e2e.json) |
| Python | 168 passed, 4 Spark-dependent skips; 92% coverage | Full suite on Python 3.13.15; the skipped cases execute in the real Spark suite |
| Spark/Delta | All 46 real tests passed offline | Shared contract, raw quarantine, MERGE, post-commit failure, checkpoint replay, audit reconciliation |
| Dashboards | BI production build and all 17 desktop/mobile BI/Streamlit browser tests passed | Current local data and archived public snapshot |
| Operations | Prometheus targets healthy; duplicate alert fired and resolved; provisioned Grafana dashboard healthy | [Operations proof](evidence/local-monitoring.json) |
| Static checks | Ruff, SQLFluff, shell examples, Compose configuration, and relative documentation links | Local verification and hosted CI |

Evidence timestamps use UTC. The JSON records contain exact run IDs and timings. Additional
monitoring scenarios change the live demo totals; the saved complete-flow proof is the baseline.
See the [evidence index](evidence/README.md) for older checks and historical results.

## What the cleanup changed

- One complete demo runner serves `make demo`, temporary `make e2e`, and CI.
- The shorter duplicate demo and overlapping feature/release trackers were removed; their useful
  behavioral checks are covered by the complete demo test.
- One canonical demo guide replaces repeated setup instructions. The old zero-cost page remains
  a compatibility link for the published 0.1.0 release.
- README and architecture distinguish the fast local path, separate Spark/Delta fixture, and
  optional Azure deployment. The cloud plan links stage runbooks instead of repeating them.
- Demo, dashboard, dbt, and monitoring commands share `DEMO_DIR`. Compose mounts the selected
  metric/data directories rather than an unrelated default folder.
- Reusing a demo directory returns a readable error and preserves its contents.
- Stage 7 accepts an interpreter override and checks that it is executable before secret/cloud work.
- The environment example uses deployment-supplied cloud values instead of a particular account.

## Public portfolio and historical Azure scope

The [public dashboard](https://pk-999.github.io/retailpulse/) serves a verified aggregate export
from **15 August 2026**, covering business dates **2010–2011**. Its £91,970.02 and 1,796 orders
belong to that archive. The [walkthrough](portfolio-walkthrough.md) is a recorded local tour,
with archived Azure and synthetic local data labeled separately.

August Azure evidence covers scoped infrastructure/access, two ADF deliveries, typed batch Delta,
Event Hubs streaming and checkpoint recovery, dbt Gold/SCD2, and a reconciled BI export. Those
runs certify their original deployments, not the refactored target-service code.

The last saved cloud observations saw ADF `Disabled` and remote state `AccountIsDisabled`.
The 9 October account check also reported a disabled subscription; the portal warned of deletion
on 11 October. Current resource existence, cloud backup, teardown, and billing status remain
unverified. No new Azure upgrade, apply, workload, or notification is part of this cleanup.

## Remaining limits

- Fresh Azure deployment, cloud alert delivery, and target-service cleanup are deferred. The
  [optional Azure plan](execution-plan.md) describes their future gates.
- The local adapter assumes one writer and completed append-only deliveries. Multiple atomic
  exports are eventual materializations, not a distributed transaction.
- Prefix hashing/export and some daily aggregate comparisons rescan history. The saved 50k-event
  observation is a workstation measurement, not production load certification.
- Older backdated ingestion needs explicit replay/full refresh. Enterprise CDC, deletes, richer
  return/cancellation behavior, and production performance certification are outside this release.
- Event purchase/view ratio is not customer conversion. Model-based incident advice is optional
  and performs no autonomous remediation.

These limits do not prevent reproduction of the local portfolio flow. They bound the claims a
reviewer should make about its deployment, scale, and business semantics.
