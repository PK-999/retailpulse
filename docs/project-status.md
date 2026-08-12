# RetailPulse project status

Status date: 2026-08-12

## Executive summary

The local vertical slice is built and verified. It generates events, performs incremental
Bronze/Silver processing, handles duplicates/late/malformed inputs, builds Gold outputs, emits
metrics and alerts, and generates an incident report.

The Azure target is prepared as Terraform, ADF, and Databricks source assets. It has not been
deployed into an Azure subscription, so cloud connectivity, permissions, job orchestration,
performance, and screenshots remain deployment work rather than completed capabilities.

The ordered implementation and verification backlog is maintained in the
[stage-wise execution plan](execution-plan.md).

## Built and verified

- Strict event contract and topic routing.
- All seven event types and five traffic/failure scenarios.
- Local incremental ingestion with durable topic checkpoints.
- Append-only Bronze output and idempotent Silver event storage.
- Duplicate detection, 30-minute late-event handling, and malformed-record quarantine.
- Pipeline audit table and JSONL audit history.
- Gold order summary and local dashboard data.
- dbt project with 10 models, one SCD2 snapshot, and 18 data tests.
- Prometheus metrics generation and threshold alerts.
- Deterministic incident analysis and report persistence.
- UCI CSV normalization.
- Python test suite, Ruff, SQLFluff, Docker Compose validation, and Terraform validation.
- End-to-end demo on Python 3.11.
- Redpanda broker health, three-topic Kafka publishing/consumption, and restart persistence.
- Live Prometheus target scraping and degraded-run metric/alert changes.
- Grafana health and five-panel dashboard provisioning through its API.
- Streamlit populated and empty-state behavior through its application test runner.
- Ollama-backed incident generation plus deterministic fallback during service unavailability.
- Clean Linux/Python 3.11 CI-equivalent execution for Ruff, pytest, demo, dbt, and SQLFluff.
- Terraform 1.9 formatting/initialization/validation with committed provider selections.

Validation evidence from the latest implementation pass:

| Check | Result |
|---|---|
| Python tests | 11 passed |
| Ruff | Passed |
| SQLFluff | Passed |
| dbt build | 29/29 nodes passed |
| Docker Compose config | Valid |
| Terraform | Valid against AzureRM 3.117.1 |
| Failure demo | 31.7% duplicate rate detected and explained |
| Stage 1 local services | Functional checks and Grafana visual QA passed; Streamlit refresh pending |
| Stage 2 GitHub/CI | Passed locally and in hosted push/PR runs; protected main requires both jobs |

## Built but requiring external integration

These components exist, but “complete” requires running them against their target services:

- Databricks batch notebook against ADLS Delta storage.
- Databricks Structured Streaming consumer against Kafka or Event Hubs.
- ADF historical ingestion against configured HTTP and ADLS datasets.
- Streamlit refreshed desktop and narrow visual review; behavior and data sections are verified.
- Terraform plan/apply against an authenticated Azure subscription.

## Remaining for the full Azure demo

### Required

1. Select the Azure subscription, region, naming convention, budget, and deployment identity.
2. Run `terraform plan`, review projected costs, and explicitly apply the infrastructure.
3. Create the ADLS directory hierarchy and least-privilege role assignments.
4. Add/import ADF linked services and datasets, then execute the historical ingestion pipeline.
5. Upload the Databricks jobs, configure account paths/secrets, and create job compute.
6. Connect the producer to Event Hubs and verify offsets, checkpoint recovery, watermarking, and
   Delta MERGE on a live cluster.
7. Configure dbt for the Databricks adapter and build Gold tables in the target catalog.
8. Connect Databricks SQL or Power BI and validate dashboard queries.
9. Configure Azure Monitor/log forwarding and verify alert delivery.
10. Run the complete clean-state demonstration and capture screenshots/video.

### Recommended portfolio polish

- Create milestone tags after the first Azure-backed release.
- Add screenshots of ADF, Databricks, dbt lineage, dashboard, Grafana, AI analysis, and CI.
- Record the planned 5–10 minute demo video.
- Add representative cost estimates and teardown instructions after the first Azure deployment.
- Add sample dashboard screenshots to the README.

### Optional enhancements

- RAG over runbooks, contracts, and dbt documentation.
- Azure Monitor alerts and a notification connector.
- Managed schema registry and contract compatibility checks.
- Governed quarantine correction/replay workflow.
- A `dim_promotion` source and model when promotion data becomes available.
- Incremental dbt models for larger volumes.
- Load/performance testing, autoscaling policy, and SLOs.
- Unity Catalog permissions and data-lineage configuration.
- Multi-environment Terraform modules and remote state.

## Known limitations

- The file-backed local adapter tests processing semantics but is not a Kafka consumer benchmark.
- Normal checkpoint continuation is tested, but the local offset file and SQLite commit are not one
  atomic transaction; abrupt process-loss fault injection remains before an exactly-once claim.
- Local SQLite/JSONL behavior does not reproduce Delta transaction or cloud storage performance.
- The ADF JSON references datasets that must be configured for the target subscription.
- Terraform intentionally omits Databricks compute and identity role assignments.
- The dashboard has functional QA but not yet screenshot-based desktop/narrow visual QA.
- Ollama model and fallback paths are verified; local CPU inference is slow and model quality still
  depends on the selected model.
- Python 3.14 is excluded because the pinned dbt 1.9 dependency stack is not compatible with it.

## Definition of done for release 1

Release 1 is done when all items under “Remaining for the full Azure demo — Required” have been
completed, the CI workflow is green in GitHub, and the demo guide can be executed from a clean
checkout without undocumented manual fixes.
