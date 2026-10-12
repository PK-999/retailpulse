# Verification evidence

Records are dated and scoped. Start with current local proof; historical cloud evidence does
not establish that Azure services are operating today.

## Current local portfolio

- [Complete demo and three dbt builds](local-e2e.json): latest isolated baseline, run IDs, totals,
  unchanged incremental results, full-refresh equivalence, and deterministic incident analysis.
- [Monitoring](local-monitoring.json): selected data path, healthy targets/Grafana, alert firing
  and recovery.
- [Spark/Delta/Kafka mechanics](local-spark-contract.md): October contract, worker, replay, and
  target-side audit proof; the cleanup also reran all 46 real Spark/Delta tests.
- [BI and Streamlit](stage-09-bi-dashboard.md): recorded browser QA and screenshots; the cleanup
  reran all 17 browser tests against the current local demo and saved snapshot.

## Release and presentation archive

- [0.1.0 clean-checkout verification](release-verification.json): original October release checks.
- [9 October zero-cost release proof](zero-cost-local-e2e.json): original checkpoint, retained unchanged.
- [Public Pages verification](public-bi-dashboard.json): deployment, six view states, snapshot identity.
- [Walkthrough media](walkthrough-media.json): original full decode and playback checks.
- [50k-event observation](local-scale-benchmark.json): bounded workstation timing, not a scale SLA.
- [Stage 1 local services](stage-01-local-verification.md), [Ollama report](stage-01-ollama-report.md),
  [rules fallback](stage-01-rules-fallback-report.md): historical integration evidence.
- [Stage 2 hosted CI](stage-02-ci-preflight.md), [Stage 3 local Spark](stage-03-local-spark.md):
  original setup and execution evidence.

## Historical August Azure results

- [Core readiness](stage-03-readiness.md), [identity/storage](stage-04-readiness.md),
  [reviewed plan](stage-03-04-plan-review.md).
- [Historical ingestion](stage-05-historical-ingestion.md), [batch Delta](stage-06-databricks-batch.md).
- [Event Hubs streaming/recovery](stage-07-eventhubs-streaming.md).
- [dbt-on-Databricks Gold/SCD2](stage-08-dbt-gold.md).
- [Azure Gold export and later browser checks](stage-09-bi-dashboard.md).

## Deferred cloud verification

[Saved preflight](cloud-monitor-preflight.json) and [monitoring evidence](stage-10-cloud-monitoring.md)
record disabled services and absent live alert proof. Refer to the [current status](../project-status.md)
and [optional Azure plan](../execution-plan.md) before interpreting these records.

Preserve original artifact dates and avoid credentials, private keys, or raw sensitive records
when adding evidence.
