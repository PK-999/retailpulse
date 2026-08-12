# RetailPulse external verification and Azure completion plan

Last reviewed: 2026-08-12

## 1. Objective

This plan moves RetailPulse from a locally verified reference implementation to a recorded,
repeatable Azure demonstration. Stages are ordered by dependency and cost: validate free local
integrations first, establish source control and CI, then create Azure resources and progressively
prove batch, streaming, analytics, monitoring, and the final demo.

Do not mark a stage complete because its files exist. Mark it complete only when its exit gate has
passed and the listed evidence has been saved.

## 2. Stage overview

| Stage | Outcome | Depends on | Estimated effort |
|---|---|---|---|
| 0 | Cloud, identity, budget, and evidence decisions recorded | None | 1–2 hours |
| 1 | Local external services verified live | Stage 0 only for evidence naming | 2–4 hours |
| 2 | Repository pushed and hosted CI green | Stage 1 | 1–3 hours |
| 3 | Reviewed Azure plan and core infrastructure deployed | Stages 0 and 2 | 2–4 hours |
| 4 | Identities, ADLS paths, secrets, and access verified | Stage 3 | 3–5 hours |
| 5 | ADF lands the historical UCI archive | Stage 4 | 2–4 hours |
| 6 | Databricks batch produces Bronze and Silver Delta | Stage 5 | 4–6 hours |
| 7 | Event Hubs streaming, recovery, and Delta MERGE verified | Stages 4 and 6 | 6–10 hours |
| 8 | dbt builds and tests Azure Gold models | Stages 6 and 7 | 3–6 hours |
| 9 | A live SQL/BI dashboard reads Gold | Stage 8 | 2–5 hours |
| 10 | Azure monitoring and alert delivery verified | Stages 5–9 | 3–6 hours |
| 11 | Clean-state end-to-end demo and evidence captured | All prior stages | 4–6 hours |
| 12 | Costs controlled and release closed | Stage 11 | 1–2 hours |

Estimated total: approximately 34–59 focused hours. Actual Azure provisioning and cluster startup
time is separate. These are planning estimates, not delivery guarantees.

## 3. Global rules

- Use one Azure environment, initially `dev`, and one naming prefix.
- Store secrets in Key Vault or the CI secret store; never put them in Git, screenshots, notebooks,
  Terraform variables, command history, or demo recordings.
- Record resource IDs, run IDs, job IDs, table versions, and timestamps with every screenshot.
- Keep Bronze immutable and preserve quarantine evidence during every failure test.
- Review the Terraform plan and estimated costs before every apply.
- Do not leave interactive Databricks compute running after validation.
- Update [project status](project-status.md) at every completed stage.

## Stage 0 — Decisions, budget, and definition of done

### Goal

Remove choices that would otherwise interrupt deployment or cause accidental spend.

### Tasks

- [ ] Select the Azure tenant and subscription.
- [ ] Confirm the deployment region after checking service availability and current pricing.
  `centralindia` is the template default, not a binding decision.
- [ ] Set a maximum monthly budget and warning thresholds appropriate to the subscription.
- [ ] Choose the resource naming prefix and keep `environment=dev` for the first deployment.
- [ ] Choose the Terraform state location. Prefer remote Azure Storage state before the first shared
  deployment; local state is acceptable only for a private disposable experiment.
- [ ] Select identities:
  - human/operator identity for initial bootstrap;
  - managed identity or Databricks Access Connector for lake access;
  - ADF managed identity for landing writes;
  - GitHub Actions OIDC identity for future CI deployments.
- [ ] Decide whether the first BI target is Databricks SQL or Power BI. Databricks SQL is the
  recommended first target because it removes a desktop/gateway dependency.
- [ ] Create an evidence directory outside generated `data/`, with filenames such as
  `stage-05-adf-success.png` and `stage-07-checkpoint-recovery.png`.
- [ ] Record teardown expectations: retain, stop, or destroy resources after the demo.

### Exit gate

A short decision record contains subscription alias, region, environment, budget ceiling,
deployment identities, state backend, BI choice, and teardown rule. It contains no secret values.

## Stage 1 — Verify local external services

### Goal

Exercise every “built but not externally verified” local integration before cloud work begins.

### 1A. Redpanda/Kafka publishing

- [x] Start Redpanda: `docker compose up -d redpanda`.
- [x] Create `customer-events`, `order-events`, and `inventory-events` with `rpk`.
- [x] Install the Kafka client (`confluent-kafka` 2.15.0 in the existing environment).
- [x] Export `KAFKA_ENABLED=true` and the local bootstrap address.
- [x] Produce a seeded normal scenario.
- [x] Consume samples with `rpk` and validate topic routing and JSON contract.
- [x] Restart Redpanda and prove broker/topic persistence.

Evidence: broker health, topic list, one valid event from each topic, and producer delivery success.

### 1B. Grafana and Prometheus

- [x] Start `prometheus`, `node-exporter`, and `grafana`.
- [x] Return to file-backed processing with `KAFKA_ENABLED=false`.
- [x] Run one normal and one duplicate scenario.
- [x] Confirm Prometheus scrapes the RetailPulse target.
- [x] Confirm the provisioned Grafana dashboard contains the five required panels.
- [x] Confirm a duplicate scenario changes Prometheus data and the active-alert value.
- [x] Visually confirm the five Grafana panels render correctly for degraded data.

Evidence: Prometheus target page and healthy/degraded Grafana screenshots.

### 1C. Streamlit visual QA

- [x] Start `streamlit run dashboard/app.py`.
- [ ] Inspect desktop and narrow-width layouts.
- [x] Verify revenue, orders, AOV, conversion, countries, products, customers, event rate, inventory,
  pipeline runs, and alerts against SQLite queries.
- [x] Confirm empty-state behavior after pointing `RETAILPULSE_DATA_DIR` at a clean directory.
- [ ] Fix any clipping, unreadable labels, empty charts, or misleading formats found during visual
  inspection. No functional rendering exceptions remain.

Evidence: annotated dashboard screenshots plus a short QA checklist.

### 1D. Ollama analysis

- [x] Start Ollama and pull the configured model.
- [x] Generate and process a duplicate scenario with `--ollama`.
- [x] Confirm the report cites only supplied run metrics and alerts.
- [x] Stop Ollama and repeat to prove `rules-fallback` behavior.
- [x] Save both reports and compare their remediation to the duplicate-event runbook.

Evidence: one model-generated report and one fallback report for the same class of incident.

### Exit gate

All four integrations have live evidence. Any failure is captured as a tracked issue before Stage 2.

Current status: functionally passed and Grafana visual QA passed. Refreshed desktop and narrow
Streamlit evidence remains open as `STG1-VIS-001`; see
[Stage 1 evidence](evidence/stage-01-local-verification.md).

## Stage 2 — GitHub repository and hosted CI

### Goal

Make the validated baseline reviewable and reproducible outside the development machine.

### Tasks

- [x] Review `git status`; ensure `.env`, generated `data/`, state, caches, and credentials are ignored.
- [ ] Create a logical initial commit or a small sequence of milestone commits.
- [ ] Create the GitHub repository and push `main`.
- [ ] Protect `main` and require the CI workflow before merge.
- [ ] Open a test pull request so the pull-request trigger is exercised.
- [x] Verify Python lint/tests, demo, dbt build/tests, SQLFluff, Terraform format, and Terraform
  validate locally in the same Python/Terraform versions as hosted CI.
- [ ] Verify both jobs pass in GitHub-hosted CI.
- [ ] Add a CI status badge only after the hosted workflow is green.
- [ ] Configure GitHub OIDC for Azure later; do not store a long-lived Azure client secret if OIDC is
  available for the selected account.

Current status: local CI preflight passed and GitHub authentication is active. Initial commit is
ready; GitHub creation/push is waiting only for the remote visibility decision. See
[Stage 2 preflight evidence](evidence/stage-02-ci-preflight.md).

### Exit gate

A clean checkout passes the hosted workflow on Python 3.11. The branch rule requires that workflow,
and no secret appears in repository history or Actions logs.

## Stage 3 — Plan and deploy core Azure infrastructure

### Goal

Create the minimum cloud boundary needed for batch and streaming validation.

### Tasks

- [ ] Add the selected remote Terraform backend configuration if required by Stage 0.
- [ ] Add an Azure budget resource or configure an equivalent subscription/resource-group budget.
- [ ] Run formatting, initialization, validation, and a saved plan.
- [ ] Review every create/change action, globally unique name, SKU, region, and estimated cost.
- [ ] Apply only the reviewed plan.
- [ ] Verify the resource group, ADLS-enabled storage, filesystem, three Event Hubs, ADF, Databricks,
  and Key Vault exist.
- [ ] Capture Terraform outputs and resource overview without exposing keys.
- [ ] Immediately check Azure Cost Management and resource health.

### Exit gate

Terraform state matches the deployed resources, the budget is active, and no unexpected resource
or billable compute exists.

## Stage 4 — Identity, ADLS, directories, and secrets

### Goal

Establish least-privilege access before running data workloads.

### Tasks

- [ ] Add a Databricks Access Connector or explicitly document the selected service principal path.
- [ ] Grant ADF’s managed identity write access at the RetailPulse filesystem or landing scope.
- [ ] Grant the Databricks access identity the minimum data-plane permissions required for the lake.
- [ ] Create `landing`, `bronze`, `silver`, `gold`, `checkpoints`, and `quarantine` paths.
- [ ] Create Key Vault secret names for any unavoidable Event Hubs SAS credentials.
- [ ] Configure Databricks secret access or Unity Catalog storage credentials/external locations.
- [ ] Prove ADF can write a harmless test file and Databricks can read/write a test Delta path.
- [ ] Prove an unauthorized identity cannot access the same path.

### Exit gate

Positive and negative access tests pass. Identity assignments and scopes are captured in a
non-secret access matrix.

## Stage 5 — ADF historical ingestion

### Goal

Land the original UCI source in ADLS through a successful, observable ADF run.

### Integration gap to resolve

The current ADF template lands the original archive, while the existing batch job expects four
normalized JSONL datasets. Preserve the archive as immutable raw input and add a preprocessing
step rather than pretending the formats already align.

### Tasks

- [ ] Create parameterized HTTP and ADLS linked services and datasets.
- [ ] Import or deploy the pipeline template.
- [ ] Parameterize source URL, target folder, and run/date partition.
- [ ] Land the archive under a path such as `landing/uci/raw/<run_id>/`.
- [ ] Add an integrity check for non-zero size and expected archive/file type.
- [ ] Add a Databricks preprocessing task that extracts the workbook and writes the four normalized
  JSONL datasets under `landing/uci/normalized/<run_id>/`.
- [ ] Add success/failure logging with ADF pipeline run ID.
- [ ] Trigger the pipeline manually and verify the raw object in ADLS.
- [ ] Rerun once to confirm the naming/idempotency policy.

### Exit gate

An ADF run is successful, its run ID maps to a raw ADLS delivery, and normalized outputs exist for
the downstream batch job without overwriting the immutable source.

## Stage 6 — Databricks batch Bronze and Silver

### Goal

Run the historical dataset through typed Delta tables with audit and quarantine evidence.

### Tasks

- [ ] Upload the preprocessing and batch notebooks as a Databricks job.
- [ ] Replace placeholder `ACCOUNT` paths with parameters or catalog/external-location references.
- [ ] Use job compute with an explicit runtime and an auto-termination policy.
- [ ] Pass ADF run ID/source path into the job.
- [ ] Create named Bronze and Silver Delta tables, not only unmanaged paths, if Unity Catalog is used.
- [ ] Verify `source_file`, `ingestion_timestamp`, and `pipeline_run_id` in Bronze.
- [ ] Verify types, null handling, deduplication, and order-item business rules in Silver.
- [ ] Inject at least one invalid historical row and confirm quarantine behavior.
- [ ] Run a second incremental delivery and prove existing records are not rebuilt incorrectly.
- [ ] Record counts read, written, and rejected in the cloud audit table.

### Exit gate

Historical Bronze/Silver Delta tables and quarantine/audit rows reconcile to the landed delivery.
The incremental rerun produces the expected changes only.

## Stage 7 — Event Hubs streaming and Delta MERGE

### Goal

Prove authenticated live events reach Delta, survive restart, and merge idempotently.

### Integration gaps to resolve

- The Python Kafka sink needs broker-specific security settings supplied through secret-backed
  configuration for Event Hubs.
- The Databricks streaming source needs the corresponding SASL/SSL options from a secret scope.
- Kafka idempotence support/configuration must be tested per broker; do not assume the local
  Redpanda setting can be copied unchanged to Event Hubs.

### Tasks

- [ ] Add non-secret Event Hubs Kafka configuration fields to application settings.
- [ ] Load credentials from environment/Key Vault and redact them from logs.
- [ ] Configure the Databricks Kafka source with secret-backed authentication.
- [ ] Use one checkpoint path per streaming query and environment.
- [ ] Start the job and produce normal traffic.
- [ ] Verify topic, partition, offset, Kafka timestamp, and ingestion timestamp in Bronze Delta.
- [ ] Verify valid events appear once in Silver after `foreachBatch` MERGE.
- [ ] Run duplicate, late-data, malformed, and traffic-spike scenarios separately.
- [ ] Confirm duplicates do not multiply Silver rows and malformed input reaches quarantine.
- [ ] Stop the streaming job during ingestion, restart it with the same checkpoint, and reconcile
  offsets/counts to prove recovery.
- [ ] Inspect Delta history and confirm MERGE operations and no multi-match failure.
- [ ] Record throughput, batch duration, processed rows/sec, and event-time latency.

### Exit gate

All five scenarios have reconciled counts, the restart resumes from the expected offsets, Silver
contains one row per event ID, and Delta history proves the MERGE path ran.

## Stage 8 — dbt on Databricks and Azure Gold

### Goal

Build the tested analytical model from cloud Silver tables.

### Tasks

- [ ] Add the `dbt-databricks` dependency and a secret-free example profile.
- [ ] Parameterize catalog, schema, HTTP path, and environment.
- [ ] Replace the local JSON staging source with declared Databricks Silver sources.
- [ ] Preserve the local DuckDB target as a separate profile/target.
- [ ] Run `dbt debug`, `dbt compile`, and `dbt build` against the dev catalog.
- [ ] Verify all dimensions, facts, aggregates, and the product SCD2 snapshot.
- [ ] Run a price change and prove a new SCD2 version is created.
- [ ] Generate dbt documentation and capture the lineage graph.
- [ ] Schedule the Gold build after batch/streaming freshness conditions are met.

### Exit gate

All models and tests pass in Databricks, Gold row counts reconcile to Silver, and SCD2 history is
demonstrated with two versions of one product.

## Stage 9 — SQL/BI dashboard

### Goal

Show business value using live Azure Gold data.

### Recommended first path: Databricks SQL

- [ ] Create or select a small SQL warehouse with auto-stop enabled.
- [ ] Build queries for revenue, orders, AOV, top products/customers, country sales, conversion,
  inventory health, and events per minute.
- [ ] Add data freshness and last-successful-run indicators.
- [ ] Validate dashboard totals directly against Gold SQL.

If Power BI is selected, additionally configure the Databricks connector, use a non-personal
authentication strategy where practical, and document refresh behavior.

### Exit gate

The dashboard uses Azure Gold—not local SQLite—and its displayed values reconcile to saved SQL
queries for one known time window.

## Stage 10 — Azure Monitor and alerting

### Goal

Detect pipeline, freshness, quality, and streaming failures outside the notebook UI.

### Tasks

- [ ] Add a Log Analytics workspace and diagnostic settings to Terraform.
- [ ] Route ADF pipeline diagnostics, Event Hubs metrics, storage diagnostics as appropriate, and
  Databricks job/audit signals to the chosen monitoring destination.
- [ ] Publish or query pipeline audit and DQ metrics.
- [ ] Create alerts for failed pipeline/job, no fresh Silver data, high duplicate/rejection rate,
  Event Hubs backlog/throttling, and excessive processing latency.
- [ ] Configure one low-risk notification destination.
- [ ] Trigger a duplicate incident and one actual stopped/failed job condition.
- [ ] Confirm alert creation, delivery, timestamps, and links to evidence/runbooks.
- [ ] Record alert noise controls and recovery/closure behavior.

### Exit gate

At least one platform failure and one data-quality failure produce delivered alerts with enough
context to locate the run and follow a runbook.

## Stage 11 — Clean-state full demonstration

### Goal

Prove the complete story without undocumented fixes and capture portfolio evidence.

### Run order

1. Trigger UCI ingestion in ADF.
2. Run Databricks preprocessing and batch Bronze/Silver.
3. Build initial Gold models with dbt.
4. Start Event Hubs publishing and Structured Streaming.
5. Show Bronze/Silver growth and dashboard changes.
6. Trigger the duplicate scenario.
7. Show DQ metrics and Azure/Grafana alerts.
8. Generate the Ollama incident report.
9. Follow the duplicate runbook and show the idempotent MERGE result.
10. Show dbt tests, lineage, Terraform state/plan, and green GitHub Actions.

### Evidence checklist

- [ ] ADF pipeline run and ADLS raw/normalized files.
- [ ] Databricks batch and streaming job runs.
- [ ] Bronze, Silver, quarantine, audit, and Delta history views.
- [ ] Checkpoint restart evidence.
- [ ] dbt build result and lineage.
- [ ] SQL/BI business dashboard.
- [ ] Grafana and Azure Monitor alerts.
- [ ] Ollama incident analysis.
- [ ] GitHub Actions result.
- [ ] Terraform outputs with sensitive values excluded.
- [ ] Five-to-ten-minute edited demo video and README thumbnails/links.

### Exit gate

A second person can follow the demo guide from a clean checkout, all screenshots have run/time
context, and the video tells the end-to-end business and operational story in under ten minutes.

## Stage 12 — Cost control, teardown, and release closure

### Goal

Leave the project safe, reproducible, and accurately documented after the demo.

### Tasks

- [ ] Stop Databricks clusters and SQL warehouses; verify auto-termination settings.
- [ ] Review Event Hubs, Log Analytics, storage, and other ongoing charges.
- [ ] Follow the Stage 0 retain/destroy decision; review any Terraform destroy plan before applying.
- [ ] Preserve only non-secret evidence and required state backups.
- [ ] Update requirements statuses from Built to Verified where evidence exists.
- [ ] Update known limitations, exact deployment instructions, cost notes, and teardown steps.
- [ ] Tag the release and record the final CI run and demo link.

### Exit gate

No unintended billable compute remains, project status matches reality, and Release 1 satisfies its
documented definition of done.

## 4. Traceability to the requested backlog

| Requested task | Planned stage |
|---|---|
| Kafka/Redpanda publishing | 1A |
| Live Grafana dashboards | 1B, then 11 |
| Streamlit browser visual QA | 1C |
| Ollama-generated analysis | 1D |
| Push repository and run GitHub-hosted CI | 2 |
| Select subscription, region, budget, and identity | 0 |
| Apply Terraform / deploy Azure infrastructure | 3 |
| Configure identities and ADLS permissions | 4 |
| Configure ADF and run ingestion | 5 |
| Deploy Databricks batch jobs and compute | 6 |
| Connect Event Hubs, Structured Streaming, recovery, and MERGE | 7 |
| Configure dbt with Databricks | 8 |
| Connect Power BI or Databricks SQL | 9 |
| Add Azure Monitor alerting | 10 |
| Capture screenshots and record demo video | 11 |

## 5. Critical path

The critical dependency chain is:

```text
Decisions and budget
  → GitHub baseline
  → Terraform deployment
  → Identity and ADLS access
  → ADF landing
  → Databricks batch
  → Event Hubs streaming
  → dbt Gold
  → SQL/BI and Azure Monitor
  → full demo and evidence
```

Local Grafana, Streamlit, and Ollama verification can run in parallel with the Stage 0 decision
work, but Azure batch and streaming work should not begin before identity and storage access pass.
