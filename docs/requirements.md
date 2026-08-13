# RetailPulse requirements

Last reviewed: 2026-08-12

## 1. Product objective

RetailPulse must demonstrate a credible retail data-engineering platform that combines historical
batch ingestion and near-real-time events, applies medallion transformations, produces analytics
marts, detects data incidents, and gives an operator evidence-based remediation guidance.

The seven-day constraint is part of the requirement. The first release favors a reliable,
explainable vertical slice over broad feature coverage.

## 2. Success criteria

The project is successful when a reviewer can:

1. generate healthy retail events and observe validated Silver output;
2. build Gold commerce metrics from validated events;
3. deliberately inject duplicate, late, or malformed data;
4. observe an audit record, DQ alert, and retained quarantine evidence;
5. generate a grounded incident report with a recommended operator action;
6. inspect equivalent Azure, Databricks, dbt, monitoring, and CI assets;
7. reproduce the local demonstration from documented commands.

## 3. Functional requirements

Status meanings:

- **Verified** — implemented and exercised successfully.
- **Built** — implementation exists and passes static/configuration validation, but needs its
  target external service for end-to-end verification.
- **Partial** — a useful subset exists; listed acceptance criteria remain.
- **Deferred** — intentionally outside the first release.

| ID | Requirement | Acceptance criteria | Status | Evidence |
|---|---|---|---|---|
| RP-BAT-001 | Normalize historical UCI retail data | One CSV command creates customers, products, orders, and order-items JSONL files | Verified | `src/retailpulse/batch.py`, `tests/test_prepare_uci.py` |
| RP-BAT-002 | Land the historical source through ADF | Triggered ADF run copies the source archive into ADLS Landing | Verified | Two successful ADF runs landed distinct immutable paths; `docs/evidence/stage-05-historical-ingestion.md` |
| RP-BAT-004 | Normalize each landed UCI delivery | A bounded task validates size/hash/archive member and writes customers, products, orders, and order-items JSONL under the ADF run ID | Verified | Two serverless job runs produced matching counts and manifests; `docs/evidence/stage-05-historical-ingestion.md` |
| RP-BAT-003 | Transform historical data into Bronze and Silver Delta | Typed ingestion adds source file, ingestion timestamp, and run ID; invalid items are quarantined | Verified | Two bounded serverless deliveries, named external Delta tables, baseline-plus-injected quarantine, zero-write incremental Silver MERGEs, and cloud audit evidence; `docs/evidence/stage-06-databricks-batch.md` |
| RP-EVT-001 | Generate seven retail event types | Valid v1 JSON is produced for product view, search, cart, checkout, purchase, payment, and inventory update | Verified | `src/retailpulse/events.py`, `tests/test_events.py` |
| RP-EVT-002 | Use three bounded topics | Events route to customer-events, order-events, or inventory-events | Verified | `src/retailpulse/contracts.py` |
| RP-EVT-003 | Publish to a Kafka-compatible broker | Producer can use file-backed local transport or idempotent Kafka publishing | Verified locally; Kafka path built | `src/retailpulse/producer.py`, `compose.yaml` |
| RP-STR-001 | Consume Kafka events with Structured Streaming | Spark reads three topics with an explicit schema and retains topic/partition/offset | Verified in Azure | Authenticated Event Hubs Kafka session processed 460 events; `docs/evidence/stage-07-eventhubs-streaming.md` |
| RP-STR-002 | Preserve immutable Bronze events | Every input is retained with raw payload and ingestion metadata | Verified in Azure | 460 coordinate-keyed Bronze rows with topic, partition, offset, Kafka timestamp, ingestion timestamp, scenario, and session lineage |
| RP-STR-003 | Produce trustworthy Silver events | Validate schema/rules, deduplicate on event ID, apply a 30-minute watermark, and checkpoint progress | Verified in Azure | 411 unique Silver event IDs, 30 quarantined records, five reconciled scenarios, watermark and checkpoint recovery evidence |
| RP-STR-004 | Perform an idempotent Delta merge | A micro-batch deduplicates source IDs before `MERGE` and inserts unseen events | Verified in Azure | Recovery batch reread 40 events; version-3 Bronze and Silver MERGEs each inserted 0 rows |
| RP-STR-005 | Develop Spark/Delta locally before Azure | Redpanda can feed a bounded local Structured Streaming job that writes Delta and performs the same Silver MERGE pattern | Verified | Python 3.11/Java 17 runner; `AvailableNow`, checkpoints, quarantine, MERGE, and replay evidence passed |
| RP-DQ-001 | Retain rejected evidence | Quarantine stores event ID when available, raw payload, type, message, and timestamp | Verified | `QuarantineRecord`, SQLite/JSONL quarantine tests |
| RP-DQ-002 | Record pipeline audits | Each run stores timing, status, read/written/rejected/duplicate/late counts, and duration | Verified | `pipeline_run_log`, CLI status, tests |
| RP-DQ-003 | Detect material quality degradation | Alert above 5% duplicates, 2% schema rejection, or 5% late events | Verified | `src/retailpulse/monitoring.py` |
| RP-GOLD-001 | Build dimensional and analytical marts | dbt builds customer/product/date dimensions, order facts, daily sales, customer 360, and inventory health | Verified locally and on Azure Databricks | `dbt/models/`; 37-node Azure dbt build passed |
| RP-GOLD-002 | Demonstrate SCD Type 2 | Product price changes create versioned snapshot rows | Verified on Azure Databricks | Product `10002` created a second version; source was restored |
| RP-GOLD-003 | Enforce analytics tests | Unique, not-null, accepted-value, relationship, quantity, price, and total tests pass | Verified | 26 Azure dbt data tests passed |
| RP-ANA-001 | Present business and operational metrics | Dashboard shows revenue, orders, AOV, conversion, countries, products, customers, inventory freshness, event rate, runs, and alerts | Verified | Populated/empty AppTest, all sections, single-day bar behavior, and live health passed; refreshed responsive screenshot evidence remains |
| RP-OBS-001 | Expose operational metrics | Prometheus can scrape record counts, DQ rates, duration, and alert count | Built | Prometheus textfile output and provisioned config |
| RP-OBS-002 | Provide an operations dashboard | Grafana is provisioned with core ingestion and DQ panels | Verified | Live degraded-data visual review passed in Stage 1 |
| RP-AI-001 | Generate incident analysis from facts | Report identifies triggered metrics, likely cause, and next action without inventing telemetry | Verified for deterministic engine | `src/retailpulse/incident.py`, generated demo report |
| RP-AI-002 | Support a local language model | Ollama can receive run/alert context; failures fall back safely to deterministic analysis | Verified | Model-backed and stopped-service fallback executions passed in Stage 1 |
| RP-INF-001 | Provision core Azure services as code | Terraform defines resource group, ADLS, opt-in Event Hubs, ADF, Databricks, Key Vault, and subscription budget | Verified in Azure | Applied remote state is drift-free; Event Hubs remains disabled |
| RP-CICD-001 | Automate quality gates | CI runs Python lint/tests, demo, dbt build/tests, SQL lint, and Terraform validation | Verified | Hosted push/PR Actions and required checks passed in Stage 2 |
| RP-COST-001 | Bound paid cloud execution | Event Hubs defaults off; Databricks uses job compute, `AvailableNow`, a 30-minute maximum, and a small Azure profile | Verified in Azure | Exact four-resource enable plan, bounded unscheduled serverless runs, automatic secret removal, Event Hubs deletion, and final drift-free plan |
| RP-SEC-001 | Use managed identities for lake access | ADF system identity and a Databricks Access Connector receive scoped data-plane roles | Verified in Azure | ADF write and Databricks Delta read/write passed; unauthorized operator access was denied |
| RP-SEC-002 | Create governed ADLS zones | Six medallion/checkpoint/quarantine directories exist as Terraform resources | Verified in Azure | All six paths exist and the Delta proof created a transaction log beneath Silver |
| RP-SEC-003 | Keep secrets out of code and state | Secret names are versioned, values enter Key Vault outside Terraform, and workload identities receive scoped secret roles | Verified boundary | Key Vault RBAC is applied; Event Hubs value is intentionally deferred while the service is disabled |
| RP-DOC-001 | Make the platform reproducible | Architecture, requirements, contract, runbooks, status, and demo steps are versioned | Verified | `docs/` and root README |

## 4. Non-functional requirements

| ID | Requirement | Current rule |
|---|---|---|
| RP-NFR-001 | Idempotency | Stable `event_id` is the Silver key; processed IDs and checkpoints survive restart. |
| RP-NFR-002 | Replayability | Bronze is append-only; quarantine records preserve raw payloads. |
| RP-NFR-003 | Observability | Every processing run emits an audit row and a current metrics snapshot. |
| RP-NFR-004 | Security | Secrets never enter source control; Azure integrations use Key Vault/managed identity where practical. |
| RP-NFR-005 | Cost control | Local-first profiles are versioned; Terraform creates no compute, defaults Event Hubs off, and defines a subscription budget. |
| RP-NFR-006 | Portability | The core demo runs without Azure credentials; cloud jobs preserve the same event contract and layer boundaries. |
| RP-NFR-007 | Compatibility | Application target is Python 3.11–3.13; CI and Docker use Python 3.11. |
| RP-NFR-008 | Testability | Scenario generation is seedable and the core pipeline can use isolated temporary storage. |

## 5. Explicit first-release boundaries

The following are not required for the initial portfolio release:

- more than three Kafka topics or more than one event schema version;
- production authentication UI or tenant isolation;
- a managed schema registry;
- automatic quarantine correction/replay;
- multi-region disaster recovery;
- autoscaling and production load certification;
- a full semantic layer or enterprise master-data-management system;
- autonomous AI remediation.

AI may recommend actions but must not mutate production state.
