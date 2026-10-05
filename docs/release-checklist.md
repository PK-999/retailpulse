# RetailPulse end-to-end release checklist

Started: 2026-10-04. Objective: finish the existing portfolio platform, prove its full local
flow, package reproducible cloud operations, and publish the static dashboard when access allows.
The prior cleanup and uncommitted BI implementation are retained.

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
- [ ] Full tests, lint, SQL checks, frontend build/browser tests, offline Terraform validation,
  local Kafka/Spark/Delta/monitoring checks, and clean-checkout verification pass.
- [ ] Final code review is addressed, runbooks/evidence are current, hosted CI and GitHub Pages
  are verified, or the exact external-access step is identified without claiming it passed.

## Ownership and scope

Spark contract, dbt correctness, and dashboard verification are independent implementation tasks.
The coordinator owns Python state/recovery, generator coherence, local orchestration, cloud
monitoring/infrastructure, release integration, documentation, and final verification.

Release 1 keeps one environment, three topics, v1 contract, SCD2 product history, static public BI,
and attended bounded Azure runs. New product subsystems and continuous public cloud compute are
outside this release. Saved August cloud proofs are historical; current runs need fresh evidence.

## Progress and decisions

- Final local Python suite:168 passed,4 Spark-dependent skips; those4 tests run in Docker,
  where all 46 Spark/Delta tests pass. Independent final review reran44 affected cases and approved.
- All 37 dbt nodes pass each clean/incremental/full-refresh build. Seven integration scenarios
  cover SCD2, timestamp ties, item-only changes, sparse input, and corrected order dates.
- BI:15 browser tests; Streamlit:2 actual browser tests; desktop/narrow screenshots retained.
- Real Redpanda16/1/14 replay counts unchanged. Prometheus/Grafana healthy; duplicate alert
  fired and resolved. Cached Ollama model produced the captured incident report.
-50k local processing observation is documented with snapshot/hash rescan limits.
- Cloud readiness is explicitly false:ADF Disabled, remote state403 AccountIsDisabled;
  no live monitoring rule, paid execution, or delivered notification. Stage 10 runbook records
  the future bounded plan and separate receipt/state evidence required after restoration.

- Baseline: 60 Python tests,94% coverage;37 local dbt nodes clean+incremental;BI lint/build;
  Terraform offline validation;local Kafka/Prometheus/Grafana passed in prior cleanup.
- Spark: exact shared contract source is bundled into the standalone cloud notebook; late records
  stay in quarantine. Decimal price text is preserved rather than silently rounded in Silver.
- dbt: timestamps at the current boundary are reread; row comparison removes unchanged merge
  input. Older backdated ingestion timestamps require an explicit replay/full refresh.
- Cloud: saved USD 10/month budget remains a reference. The workspace free-credit exception ended
  2026-08-19; current account state, costs, and a concrete plan must precede paid verification.
