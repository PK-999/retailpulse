# RetailPulse project status

Release scope reviewed: 2026-10-09 (IST); evidence timestamps use UTC. The selected finish is
the local portfolio release with no additional Azure spending. The local platform and public
snapshot application are implemented and verified. Azure integration was exercised in August;
fresh target-service verification is deferred, as recorded below. Follow the
[step-by-step finish guide](zero-cost-finish.md).

## Zero-cost release checkpoint

The [9 October isolated local run](evidence/zero-cost-local-e2e.json) passed generation,
classification, DQ alerts, deterministic incident analysis, and all three dbt builds. It produced
295 Bronze, 266 Silver, 19 duplicates, 10 quarantine, 10 orders, 57 units, and £268.55. Each build
passed 37 nodes; unchanged incremental results and full-refresh equivalence were verified.
Ten local orchestration/recovery/dashboard tests passed. The production BI build and all 17
desktop/mobile browser tests passed, including the running Streamlit app against that fresh data.
The public snapshot was fetched successfully and matched the committed archive byte for byte.
The broader verification results below retain their original October release evidence dates.

The public dashboard and walkthrough remain available independently of Azure. The archived
snapshot keeps its 15 August export timestamp. Current local proof and historical cloud proof
have separate scopes; a fresh Azure session is not a completion requirement for this release.

## Current release verification

| Component | Result and scope |
|---|---|
| Python | 169 passed, 4 Spark-dependent skips on Python 3.13.15; those 4 execute in the separate real Spark suite. Coverage: 92%. CI target: 3.11. |
| Contract parity | Exact shared model source runs in Python, isolated Spark workers, and bundled Databricks notebook; strict JSON/version/UUID/business/topic checks. |
| Spark/Delta | 46 real tests passed in 25.18s, including worker TZ=Asia/Kolkata, raw quarantine, legacy price representation, intentional post-MERGE failure, checkpoint replay, and target-side duplicate audit reconciliation. |
| Kafka/Redpanda | Actual local entrypoint: 16 Bronze, 1 Silver, 14 quarantine; same-checkpoint resume preserved counts and Silver version 0. |
| Recovery | SQLite commits input offsets/raw/classifications together. Real process exits before/after commit preserve replay/audit and do not duplicate quarantine. Atomic exports are readable by Docker users. |
| Complete local command | 295 Bronze = 266 Silver + 19 duplicates + 10 quarantine; 10 orders, 57 units, £268.55. All 37 dbt nodes pass clean, incremental, and full refresh; marts reconcile and unchanged reruns stay unchanged. |
| dbt correctness | Tied timestamps, item-only arrivals, empty/sparse input, SCD2 history, corrected order dates with empty/populated previous dates; 7 behavioral integration cases. Cloud SQL/hooks run offline with Databricks credentials in DuckDB. Generated paused-job JSON keeps the standard managed warehouse profile separate from local defaults. |
| Money | Exact price text in Silver; unit price rounded half up to 2dp before Gold multiplication. SQLite/Streamlit/dbt agree for fractional prices. Unrepresentable Gold values fail while raw Silver is retained. |
| Generator | Order/customer/country identities are stable across independently seeded batches; purchase/view ratio is explicitly an event ratio. |
| BI frontend | 15 Chromium tests passed: 3 views at 1440px/390px, keyboard tabs, no overflow/runtime errors, malformed/empty/retry/freshness/public-boundary cases. |
| Streamlit | AppTest plus actual desktop/narrow browser tests and screenshots; local operational fixture after extra duplicate test: 287 Silver, 10 orders, £286.97. Newly built Docker image also passes both browser tests as UID 10001 with read-only data. |
| Local operations | Prometheus targets up; duplicate alert Fired then Resolved; Grafana health and provisioned Operations dashboard passed. |
| Incident analysis | Actual cached local llama3.1 model returned a grounded 4-section report; unavailable-model fallback retained deterministic guidance. |
| Scale | 50,000 file-backed events: 3.423s generation, 1.550s initial processing, 0.670s no-op snapshot/hash scan; 0.043s Gold rebuild. One bounded workstation observation, not a performance SLA. |
| Static checks | Ruff, SQLFluff, TypeScript/ESLint/Vite, Docker Compose, shell syntax, notebook bundle compile, Terraform 1.15.8/AzureRM 5.0.1 offline fmt/validate pass. |
| Cloud monitoring | Optional default-off ADF failure metric alert/storage archive; 14 verifier fixtures pass. No deployment or notification delivery claimed. |
| Hosted CI | All 4 jobs passed for the final reviewed release: Python 3.11, BI, actual Spark/Delta, and Terraform. [Run](https://github.com/PK-999/retailpulse/actions/runs/37253272365). |
| Publication | [GitHub Pages](https://pk-999.github.io/retailpulse/) deployed successfully. All 6 public desktop/mobile view states, keyboard controls, snapshot byte identity, and malformed-data controls pass. |
| Walkthrough | Actual 5:11.5 MP4; full H.264 decode and Chromium playback through the end pass. |

See [local proof](evidence/local-e2e.json), [Spark/Kafka proof](evidence/local-spark-contract.md),
[operations proof](evidence/local-monitoring.json), [scale observation](evidence/local-scale-benchmark.json),
[BI evidence](evidence/stage-09-bi-dashboard.md), and [release checklist](release-checklist.md).
See [release verification](evidence/release-verification.json),
[public browser evidence](evidence/public-bi-dashboard.json), and the
[recorded walkthrough](portfolio-walkthrough.md). [PR #4](https://github.com/PK-999/retailpulse/pull/4)
is merged into `main`; the publication workflow passed its build and deploy jobs.

## Refactor and reliability changes

- Removed duplicate dbt profile and unused wrapper/environment/dependency entries.
- Centralized Gold Delta configuration and split optional dependencies by execution purpose.
- Replaced the redundant event registry with Silver's primary key; legacy stored data is retained.
- Migrated legacy exact prices/queries/raw history/checkpoints transactionally and tested retries.
- Replaced independent file checkpoints/append-on-failure outputs with a transactional input ledger
  and atomic derived files, including audit and failed-run metrics.
- Bundled the exact shared contract into standalone cloud uploads; retained aware UTC values,
  precise prices, and explicit late/representation quarantine rather than silent eviction/rounding.
- Corrected Spark batch-session merge lookup and stale no-op Delta history audit metrics.
- Reconciled replay and later-batch duplicates against actual Silver MERGE insertions.
- Fixed incremental timestamp ties/item-only changes/old daily dates and demonstrated SCD2 history.
- Hardened public snapshot validation/reconciliation/error handling and separated export age from
  historical business dates. Warehouse cleanup now verifies STOPPED with bounded retries.
- Added reproducible browser/Spark/Databricks-fixture CI gates, monitored failure rules, and a
  safe one-command isolated local demonstration.

## Historical Azure proofs

| Stage | Saved August result |
|---|---|
|3–4 | Infrastructure/lake zones/scoped identities; positive ADF/Databricks and negative operator access. |
|5 | Two immutable ADF deliveries and normalized four-entity outputs. |
|6 | Typed batch Delta, source/injected quarantine, zero-write Silver rerun. |
|7 |460 Bronze,411 unique Silver,30 quarantine;40-event checkpoint replay inserted zero Bronze/Silver rows. |
|8 |637 customers,199 products,4,518 items,£91,970.02 reconciled; no-op MERGEs and SCD2 proof. |
|9 | Validated Azure Gold export passed5 reconciliation checks; saved public snapshot has its original export timestamp. |

These results describe earlier code/deployments. The refactored cloud notebook, changed dbt
models, monitoring, and cleanup require a fresh attended Azure run before their target-service
verification can be claimed.

## Deferred Azure verification and release limits

The current [Azure preflight](evidence/cloud-monitor-preflight.json) sees ADF `Disabled`, no
monitor rule, and no Fired/Resolved cloud alert. Remote Terraform state access returns
`403 AccountIsDisabled`. Account authentication and resource listing do not establish operational
health. The 9 October account refresh also reports the subscription `Disabled`; the supplied
portal warning says the expired trial will be deleted on 11 October. The selected release uses
no subscription upgrade, apply, paid job, or notification send. Repository artifacts are retained,
but they are not a backup of the disabled lake or remote state, and Azure teardown is not claimed.
The August free-credit exception expired 2026-08-19; the USD 10 budget notifies and does not cap
spend. If a future cloud session is separately authorized, restore services, rerun preflight,
review the bounded plan, and follow [Stage 10](runbooks/stage-10-cloud-monitoring.md).

- The local adapter assumes one attended writer and completed append-only file deliveries.
  Exports are eventual materializations, not a multi-file distributed transaction.
- Lateness is event-time versus ingestion-time classification; no stateful watermark eviction
  silently removes rejected records. New checkpoint namespaces avoid incompatible old Spark state.
- Prefix hashing and snapshot export reread local history. Daily-sales comparison rereads current
  Gold aggregates to repair moved dates. Scale beyond this bounded demo needs measured optimization.
- Backdated ingestion before an incremental boundary needs explicit full refresh/replay. Deletes,
  enterprise CDC, richer return/cancellation semantics, and production load certification are
  outside this release.
- The local language model is advisory; deterministic detection and retained telemetry are the
  authority. No autonomous remediation is performed.
- The workspace's old `.venv` uses unsupported Python 3.14. The current local finish uses
  `.venv313` with Python 3.13.15. Cloud scripts need interpreter review before future use;
  Stage 7 currently selects `.venv` directly.
