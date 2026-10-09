# RetailPulse end-to-end release checklist

Started: 2026-10-04. Objective: finish the portfolio platform, prove its full local flow,
package reproducible cloud operations, and publish the static dashboard.

Release scope selected on 2026-10-09: finish with **no additional Azure spending**, using fresh
local proof, the existing published dashboard, and clearly dated historical Azure evidence.
The [finish guide](zero-cost-finish.md) is the active route; pending cloud gates are deferred
and remain unverified.

## Completion criteria

- [x] Python and Spark enforce the same versioned contract and routing; malformed and late input
  is retained with reasons, duplicates/replays do not corrupt Silver, cloud notebook shipping is reproducible.
- [x] dbt handles tied ingestion timestamps, item-only arrivals, empty/sparse input, unchanged
  reruns, and reconciles incremental results with a full refresh.
- [x] Synthetic order/customer/country relationships are consistent; event-ratio metrics are labeled explicitly.
- [x] Local input offsets and classified records commit together; crash recovery repairs atomic
  materializations without losing events or duplicating quarantine; audit and failed-run metrics are available.
- [x] A single attended local command proves generation → ingestion → Silver → dbt Gold →
  metrics → incident output with isolated data, plus failure injection and reconciliation.
- [x] Frontend and Streamlit pass desktop/narrow browser QA with evidence; stale snapshot state,
  schema errors, export reconciliation, and public-data boundaries are verified.
- [x] Cloud monitoring definitions, alert verification runner, deployment preflight, and bounded
  orchestration are complete, with cost scope recorded before any paid execution.
- [x] Full tests, lint, SQL checks, frontend build/browser tests, offline Terraform validation,
  local Kafka/Spark/Delta/monitoring checks, and clean-checkout verification pass.
- [x] Final code review is addressed, runbooks/evidence are current, hosted CI and GitHub Pages
  are verified, or the exact external-access step is identified without claiming it passed.

## Release scope

Release 0.1.0 keeps one environment, three topics, v1 contract, SCD2 product history, and static
public BI. Azure assets and saved August proofs are retained for reference; fresh attended Azure
runs are optional future verification. New product subsystems and continuous public cloud compute
are outside this release. Historical cloud proofs do not certify the refactored deployment.

## Progress and decisions

- On 9 October, the zero-cost finish was selected. The isolated local flow was rerun successfully:
  295 Bronze = 266 Silver + 19 duplicates + 10 quarantine; 10 orders, 57 units, £268.55;
  all 37 dbt nodes passed in each clean/incremental/full-refresh build. See
  [fresh local proof](evidence/zero-cost-local-e2e.json). No Azure workload was started.
- Ten orchestration/recovery/dashboard tests and all 17 desktop/mobile BI/Streamlit browser tests
  passed. The BI production build passed. The public JSON still matches the committed archived
  export, with SHA-256 `0986183d63a1c691d63645cdd950083c07ebb82a17276ea05a89100e10ddaa3e`.
- The refreshed Azure account listing reports `Disabled`. The user-supplied portal warning says
  the expired trial will be deleted on 11 October. Current repository artifacts are independent
  of Azure, but lake/state backup, target-service cleanup, and billing status are not verified.

- Release [PR #4](https://github.com/PK-999/retailpulse/pull/4) is merged; all 4 hosted CI jobs
  passed. [GitHub Pages](https://pk-999.github.io/retailpulse/) build/deployment passed and actual
  public browser QA verified all 6 desktop/mobile views, keyboard controls, byte-identical
  snapshot data, and malformed-data rejection. See [release evidence](evidence/release-verification.json).
- The 5:11.5 [walkthrough](portfolio-walkthrough.md) has full decode and browser playback proof.
  Owned local test services were stopped after verification.
- Final local Python suite: 169 passed, 4 Spark-dependent skips; those 4 tests run in Docker,
  where all 46 Spark/Delta tests pass. Coverage is 92%. Independent review reran 44 affected
  cases; subsequent automated-review regressions cover managed dbt profiles and duplicate audits.
- All 37 dbt nodes pass each clean/incremental/full-refresh build. Seven integration scenarios
  cover SCD2, timestamp ties, item-only changes, sparse input, and corrected order dates.
- BI: 15 browser tests; Streamlit: 2 actual browser tests, also passing against the new non-root
  Docker image with read-only data; desktop/narrow screenshots retained.
- Real Redpanda 16/1/14 replay counts unchanged. Prometheus/Grafana healthy; duplicate alert
  fired and resolved. Cached Ollama model produced the captured incident report.
- 50k local processing observation is documented with snapshot/hash rescan limits.
- Cloud readiness is explicitly false: ADF Disabled, remote state 403 AccountIsDisabled;
  no live monitoring rule, paid execution, or delivered notification. Stage 10 runbook records
  the future bounded plan and separate receipt/state evidence required after restoration.

- Baseline: 60 Python tests, 94% coverage; 37 local dbt nodes clean+incremental; BI lint/build;
  Terraform offline validation; local Kafka/Prometheus/Grafana passed in prior cleanup.
- Spark: exact shared contract source is bundled into the standalone cloud notebook; late records
  stay in quarantine. Decimal price text is preserved rather than silently rounded in Silver.
- dbt: timestamps at the current boundary are reread; row comparison removes unchanged merge
  input. Older backdated ingestion timestamps require an explicit replay/full refresh.
- Cloud: saved USD 10/month budget remains a reference. The workspace free-credit exception ended
  2026-08-19; current account state, costs, and a concrete plan must precede paid verification.
