# RetailPulse project status

Status date: 2026-08-12

## Executive summary

The local vertical slice is built and verified. It generates events, performs incremental
Bronze/Silver processing, handles duplicates/late/malformed inputs, builds Gold outputs, emits
metrics and alerts, and generates an incident report.

The minimum-cost Azure foundation is deployed and drift-free. ADLS, ADF, Azure Databricks, Key
Vault, the Databricks Access Connector, scoped identity roles, lake directories, and the
subscription budget are live. ADF managed-identity write access, Unity Catalog external-location
access, a bounded Delta MERGE, and an unauthorized-access denial have all passed. Event Hubs and
classic compute remain intentionally absent, and the platform-created starter SQL warehouse is
stopped.

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
- Hosted GitHub Actions execution with protected required checks.
- Reproducible Python 3.11/Java 17 local Spark runner with bounded Kafka ingestion, Delta MERGE,
  quarantine, checkpoints, and replay-idempotency evidence.
- Azure remote Terraform state, drift-free core deployment, subscription budget, and explicit
  cost controls.
- Least-privilege ADF and Databricks identities at the filesystem boundary.
- Live ADF managed-identity write, Databricks external Delta read/write/MERGE, and negative access
  tests.
- Two live ADF UCI archive deliveries with immutable run-ID paths, archive integrity gates, and
  matching four-dataset Databricks normalization outputs.
- Live bounded Databricks historical Bronze/Silver processing with 10 named external Unity Catalog
  Delta tables, source-quality quarantine, audit rows, and a zero-write incremental Silver proof.

Validation evidence from the latest implementation pass:

| Check | Result |
|---|---|
| Python tests | 25 passed |
| Ruff | Passed, including local and Databricks Spark jobs |
| SQLFluff | Passed |
| dbt build | 29/29 nodes passed on initial and incremental reruns |
| Docker Compose config | Valid |
| Terraform | Formatted and valid against Terraform 1.15.8 / AzureRM 5.0.1 |
| Failure demo | 31.7% duplicate rate detected and explained |
| Stage 1 local services | Functional checks and Grafana visual QA passed; Streamlit refresh pending |
| Stage 2 GitHub/CI | Passed locally and in hosted push/PR runs; protected main requires both jobs |
| Stage 3 Azure foundation | Applied and drift-free; Event Hubs/classic compute absent |
| Stage 4 identity/storage | Positive ADF/Databricks and negative operator access tests passed |
| Stage 5 historical ingestion | Two ADF deliveries and two normalized four-dataset outputs passed |
| Stage 6 Databricks batch | Two deliveries passed; 56 source rejections + 1 injected rejection; Silver rerun wrote 0 rows |

## Built but requiring external integration

These components exist, but their later-stage production paths still require target-service runs:

- Databricks Structured Streaming consumer against Kafka or Event Hubs.
- Refreshed Streamlit desktop and narrow visual screenshots; functional, empty-state, section, and
  single-day revenue-bar checks are automated and passing.

## Remaining for the full Azure demo

### Required

1. Temporarily enable Event Hubs, verify offsets/checkpoint recovery/watermarking/Delta MERGE on a
  bounded job run, then disable Event Hubs.
2. Configure dbt for the Databricks adapter and build Gold tables in the target catalog.
3. Connect Databricks SQL or Power BI and validate dashboard queries.
4. Configure Azure Monitor/log forwarding and verify alert delivery.
5. Run the complete clean-state demonstration and capture screenshots/video.

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
- Fine-grained Unity Catalog grants, workspace binding, and lineage configuration beyond the
  verified Stage 4 storage credential/external location.
- Multi-environment Terraform modules and remote state.

## Known limitations

- The file-backed local adapter tests processing semantics but is not a Kafka consumer benchmark.
- Normal checkpoint continuation is tested, but the local offset file and SQLite commit are not one
  atomic transaction; abrupt process-loss fault injection remains before an exactly-once claim.
- Local Spark/Delta can reproduce transaction and streaming logic but not Event Hubs, ADLS,
  managed identity, or Azure performance.
- Stage 5 normalizes the full 541,909-row workbook with pandas on bounded serverless compute; this
  is an integration proof, not a preferred large-scale Excel ingestion benchmark.
- Terraform intentionally omits Databricks compute; identity role assignments are now applied.
- The dashboard has functional QA and a live healthy server; refreshed desktop/narrow screenshots
  remain because the browser surface was unavailable during the closure run.
- Ollama model and fallback paths are verified; local CPU inference is slow and model quality still
  depends on the selected model.
- Python 3.14 is excluded because the pinned dbt 1.9 dependency stack is not compatible with it.

## Definition of done for release 1

Release 1 is done when all items under “Remaining for the full Azure demo — Required” have been
completed, the CI workflow is green in GitHub, and the demo guide can be executed from a clean
checkout without undocumented manual fixes.
