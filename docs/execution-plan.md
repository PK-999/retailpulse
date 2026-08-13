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
- Develop Spark/Delta locally with `dev` or `demo`; use `azure` only for bounded integration proof.
- Keep Event Hubs disabled outside the Stage 7 streaming window.
- Update [project status](project-status.md) at every completed stage.

## Stage 0 — Decisions, budget, and definition of done

### Goal

Remove choices that would otherwise interrupt deployment or cause accidental spend.

### Tasks

- [x] Select the Azure tenant and subscription.
- [x] Confirm the deployment region after checking service availability and current pricing.
  `centralindia` is the template default, not a binding decision.
- [x] Set a maximum monthly budget and warning thresholds appropriate to the subscription.
- [x] Choose the resource naming prefix and keep `environment=dev` for the first deployment.
- [x] Choose the Terraform state location. Prefer remote Azure Storage state before the first shared
  deployment; local state is acceptable only for a private disposable experiment.
- [x] Select identities:
  - human/operator identity for initial bootstrap;
  - managed identity or Databricks Access Connector for lake access;
  - ADF managed identity for landing writes;
  - GitHub Actions OIDC identity for future CI deployments.
- [x] Decide whether the first BI target is Databricks SQL or Power BI. Databricks SQL is the
  recommended first target because it removes a desktop/gateway dependency.
- [x] Create an evidence directory outside generated `data/`, with filenames such as
  `stage-05-adf-success.png` and `stage-07-checkpoint-recovery.png`.
- [x] Record teardown expectations: retain, stop, or destroy resources after the demo.

Current status: complete. See [the Azure deployment decision record](decisions/azure-deployment.md)
and the versioned `docs/evidence/` directory.

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

Current status: functionally passed and Grafana visual QA passed. Automated Streamlit checks cover
populated state, empty state, all required sections, and the single-day revenue bar. Refreshed
desktop and narrow Streamlit evidence remains open as `STG1-VIS-001`; see
[Stage 1 evidence](evidence/stage-01-local-verification.md).

## Stage 2 — GitHub repository and hosted CI

### Goal

Make the validated baseline reviewable and reproducible outside the development machine.

### Tasks

- [x] Review `git status`; ensure `.env`, generated `data/`, state, caches, and credentials are ignored.
- [x] Create a logical initial commit or a small sequence of milestone commits.
- [x] Create the public `PK-999/retailpulse` GitHub repository and push `main`.
- [x] Protect `main` and require the `python` and `terraform` CI checks before merge.
- [x] Open pull request #1 and pass both required jobs through the `pull_request` trigger.
- [x] Verify Python lint/tests, demo, dbt build/tests, SQLFluff, Terraform format, and Terraform
  validate locally in the same Python/Terraform versions as hosted CI.
- [x] Verify both jobs pass in GitHub-hosted CI.
- [x] Add a CI status badge only after the hosted workflow is green.
- [x] Record GitHub OIDC as the required authentication method for a future Azure deployment
  workflow; create the federated credential only when that workflow and its Azure scope are
  reviewed. No long-lived Azure client secret is stored.

Current status: complete. The public repository, hosted push and pull-request runs, required checks,
branch protection, test pull request, and badge passed the exit gate. See
[Stage 2 preflight evidence](evidence/stage-02-ci-preflight.md).

### Exit gate

A clean checkout passes the hosted workflow on Python 3.11. The branch rule requires that workflow,
and no secret appears in repository history or Actions logs.

## Stage 3 — Plan and deploy core Azure infrastructure

### Goal

Create the minimum cloud boundary needed for later validation without starting streaming charges.

### Tasks

- [x] Install `.[spark]` under Python 3.11 with a compatible Java runtime.
- [x] Start Redpanda, publish a small `dev` sample, and run the local Spark job with its default
  `AvailableNow` trigger.
- [x] Verify local Bronze, Silver, quarantine, checkpoints, and an idempotent second MERGE before
  paying for the equivalent Azure run.
- [x] Add the selected remote Terraform backend configuration if required by Stage 0.
- [x] Add and verify the subscription budget defined by Terraform.
- [x] Run formatting, initialization, validation, and a saved plan.
- [x] Review every create/change action, globally unique name, SKU, region, and estimated cost.
- [x] Apply only the reviewed plan.
- [x] Keep `enable_event_hubs=false` for the first apply.
- [x] Verify the resource group, ADLS-enabled storage, filesystem, ADF, Databricks workspace, and
  Key Vault exist; verify that no classic cluster, running SQL warehouse, or Event Hubs namespace
  exists. The platform-created starter warehouse exists but is stopped.
- [x] Capture Terraform outputs and resource overview without exposing keys.
- [x] Check resource health, budget coverage, and managed-resource cost implications immediately;
  Cost Management actuals remain delayed/rate-limited and require a later portal refresh.

Stage 3 is complete. The reproducible runner uses Python 3.11.13, OpenJDK 17, PySpark 4.0.4, and
Delta 4.0.0. Its bounded Redpanda proof verified Bronze retention, malformed quarantine, all three
checkpoints, a recorded incremental MERGE, and an all-matched replay that left Silver unchanged.
See [Stage 3 local Spark evidence](evidence/stage-03-local-spark.md).

Cloud infrastructure prerequisites for Stage 4 are complete and Terraform is drift-free. The
workspace includes a stopped, platform-created serverless starter warehouse and managed NAT
networking; neither was active Databricks compute at the gate.

### Exit gate

Terraform state matches the deployed resources, the subscription budget is active, and no
unexpected resource, Event Hubs namespace, or billable compute exists.

## Stage 4 — Identity, ADLS, directories, and secrets

### Goal

Establish least-privilege access before running data workloads.

### Tasks

- [x] Add a system-assigned Databricks Access Connector to Terraform.
- [x] Define ADF managed-identity write access at the RetailPulse filesystem scope.
- [x] Define filesystem-scoped Databricks Access Connector data-plane access.
- [x] Define `landing`, `bronze`, `silver`, `gold`, `checkpoints`, and `quarantine` paths.
- [x] Define the Event Hubs Key Vault secret name without placing its value in Terraform state.
- [x] Configure Databricks secret access or Unity Catalog storage credentials/external locations.
- [x] Prove ADF can write a harmless test file and Databricks can read/write a test Delta path.
- [x] Prove an unauthorized identity cannot access the same path.

Current status: complete. Managed-identity roles are applied, the Unity Catalog credential and
external location validate, ADF wrote its access-test file, Databricks created/read an external
Delta table, and an operator without a storage data role was denied Azure AD data-plane access.
Event Hubs remains disabled, so its secret value is correctly deferred to Stage 7.

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

- [x] Create parameterized HTTP and ADLS linked services and datasets.
- [x] Import or deploy the pipeline template.
- [x] Parameterize source URL, target folder, and run partition.
- [x] Land the archive under `landing/uci/raw/<run_id>/`.
- [x] Add an integrity check for non-zero size and expected archive/file type.
- [x] Add a Databricks preprocessing task that extracts the workbook and writes the four normalized
  JSONL datasets under `landing/uci/normalized/<run_id>/`.
- [x] Add success/failure logging with ADF pipeline run ID.
- [x] Trigger the pipeline manually and verify the raw object in ADLS.
- [x] Rerun once to confirm the naming/idempotency policy.

Current status: complete. Two successful ADF runs landed the same SHA-256-pinned source into
distinct run-ID paths. Two bounded Databricks serverless job runs produced matching customers,
products, orders, and order-item counts in corresponding immutable normalized paths. The job is
unscheduled, no run remains active, no classic cluster exists, and the starter SQL warehouse is
stopped. See [Stage 5 evidence](evidence/stage-05-historical-ingestion.md).

### Exit gate

An ADF run is successful, its run ID maps to a raw ADLS delivery, and normalized outputs exist for
the downstream batch job without overwriting the immutable source.

## Stage 6 — Databricks batch Bronze and Silver

### Goal

Run the historical dataset through typed Delta tables with audit and quarantine evidence.

### Tasks

- [x] Upload the preprocessing and batch notebooks as Databricks jobs.
- [x] Replace placeholder `ACCOUNT` paths with parameters and Unity Catalog/external-location
  references.
- [x] Use job/serverless-job compute; prohibit all-purpose compute unless a reviewed exception sets
  10-minute automatic termination.
- [x] Set a job timeout of no more than 30 minutes and process only the `azure` profile volume.
- [x] Pass ADF run ID/source path into the job.
- [x] Create named Bronze and Silver Delta tables, not only unmanaged paths, if Unity Catalog is used.
- [x] Verify `source_file`, `ingestion_timestamp`, and `pipeline_run_id` in Bronze.
- [x] Verify types, null handling, deduplication, and order-item business rules in Silver.
- [x] Inject at least one invalid historical row and confirm quarantine behavior.
- [x] Run a second incremental delivery and prove existing records are not rebuilt incorrectly.
- [x] Record counts read, written, and rejected in the cloud audit table.
- [x] Capture input/output bytes, network/shuffle transfer, spill, duration, and Delta operation
  metrics.

Current status: complete. Two bounded, unscheduled `STANDARD` serverless runs consumed the two
immutable Stage 5 deliveries. The first established the source-quality baseline of 56 rejected
order items; the second rejected those same 56 plus exactly one injected invalid item. Silver
totals were unchanged, every second-run Silver MERGE wrote zero rows, and the audit table contains
one row per ADF run ID. See [Stage 6 evidence](evidence/stage-06-databricks-batch.md).

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

- [x] Add non-secret Event Hubs Kafka configuration fields to application settings.
- [x] Review and apply `enable_event_hubs=true` immediately before this stage.
- [x] Load credentials from environment/Key Vault and redact them from logs.
- [x] Configure the Databricks Kafka source with secret-backed authentication.
- [x] Use one checkpoint path per streaming query and environment.
- [x] Start the job and produce normal traffic.
- [x] Use `AvailableNow` for all serverless ingestion/reconciliation and restart-proof runs, with a
  hard 30-minute runtime. Serverless jobs reject processing-time triggers, so simulate interruption
  by failing after Delta commits but before Spark commits the checkpoint, then resume the same
  `AvailableNow` checkpoint.
- [x] Verify topic, partition, offset, Kafka timestamp, and ingestion timestamp in Bronze Delta.
- [x] Verify valid events appear once in Silver after `foreachBatch` MERGE.
- [x] Run duplicate, late-data, malformed, and traffic-spike scenarios separately.
- [x] Confirm duplicates do not multiply Silver rows and malformed input reaches quarantine.
- [x] Stop the streaming job during ingestion, restart it with the same checkpoint, and reconcile
  offsets/counts to prove recovery.
- [x] Inspect Delta history and confirm MERGE operations and no multi-match failure.
- [x] Record throughput, batch duration, processed rows/sec, and event-time latency.
- [x] Apply `enable_event_hubs=false` immediately after evidence capture and verify deletion.

Current status: complete. An authenticated Event Hubs Kafka session processed all five scenarios,
then deliberately failed after committing a 40-record recovery micro-batch but before checkpoint
commit. Restarting the same `AvailableNow` checkpoint reread batch 1 and produced zero-row Bronze
and Silver MERGEs. Event Hubs and temporary secrets were removed after evidence capture. See
[Stage 7 evidence](evidence/stage-07-eventhubs-streaming.md).

### Exit gate

All five scenarios have reconciled counts, the restart resumes from the expected offsets, Silver
contains one row per event ID, and Delta history proves the MERGE path ran.

## Stage 8 — dbt on Databricks and Azure Gold

### Goal

Build the tested analytical model from cloud Silver tables.

### Tasks

- [x] Add the `dbt-databricks` dependency and a secret-free example profile.
- [x] Parameterize catalog, schema, HTTP path, and environment.
- [x] Replace the local JSON staging source with declared Databricks Silver sources.
- [x] Preserve the local DuckDB target as a separate profile/target.
- [x] Preserve incremental materializations for order items, orders, and daily sales; prove a second
  run processes changed keys/dates rather than rebuilding the full tables.
- [x] Run `dbt debug`, `dbt compile`, and `dbt build` against the dev catalog.
- [x] Verify all dimensions, facts, aggregates, and the product SCD2 snapshot.
- [x] Run a price change and prove a new SCD2 version is created.
- [x] Generate dbt documentation and capture the lineage graph.
- [x] Schedule the Gold build after batch/streaming freshness conditions are met.

Current status: complete. Both the initial and no-change builds passed all 37 dbt nodes. Gold
counts and revenue reconcile exactly to Silver, all three incremental models recorded zero-source
Delta MERGEs on the second run, and product `10002` recorded a second SCD2 version before its
source price was restored. A freshness-gated weekly job is deployed in `PAUSED` state. See
[Stage 8 evidence](evidence/stage-08-dbt-gold.md). Its manually triggered hosted verification run
passed the Silver gate and all 37 dbt nodes from the pushed Git commit.

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
- [ ] Verify `enable_event_hubs=false` and that the namespace no longer exists.
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
