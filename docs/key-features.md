# RetailPulse key features

## Batch engineering

- UCI Online Retail CSV normalization into customers, products, orders, and order items.
- ADF copy-pipeline template for historical source landing.
- Typed Databricks batch ingestion with Bronze audit metadata.
- Silver duplicate removal, type conversion, business validation, and item quarantine.

## Streaming engineering

- Seedable simulator for seven event types.
- Three-topic routing for customer, order, and inventory activity.
- Normal, duplicate, late-data, malformed, and traffic-spike scenarios.
- File-backed deterministic local transport plus idempotent Kafka publishing.
- Structured Streaming consumer with explicit JSON schema and Kafka coordinates.
- Thirty-minute watermark, `event_id` deduplication, independent checkpoints, and Delta MERGE.
- Local PySpark/Delta consumer with the same bounded Kafka-to-medallion pattern.
- `AvailableNow` by default and a hard 30-minute limit for continuous demonstration mode.

## Data quality and governance

- Strict event contract with unknown-field rejection.
- Positive purchase/inventory quantities and non-negative price rules.
- Append-only Bronze records for replay and audit.
- Quarantine records with raw payload and actionable validation context.
- Durable `pipeline_run_log` with timing and outcome counts.
- Threshold-based alerts for duplicates, rejected records, and late events.

## Analytics

- dbt staging, intermediate, mart, and snapshot layers.
- Customer, product, and date dimensions.
- Order and order-item facts.
- Daily sales, customer 360, and inventory health marts.
- Incremental order-item, order, and daily-sales models keyed at their natural update grains.
- SCD Type 2 product price history.
- Unique, non-null, accepted-value, relationship, and custom business tests.
- Streamlit dashboard for business KPIs and pipeline operations.

## Observability and incident response

- Prometheus metrics for records processed, DQ rates, duration, and alert count.
- Provisioned Grafana datasource and RetailPulse operations dashboard.
- Deterministic incident analysis that works without a model server.
- Optional Ollama analysis with safe rules fallback.
- Duplicate-event and malformed-event operator runbooks.

## Platform engineering

- Docker image and Compose services for Redpanda, Prometheus, Grafana, Ollama, and dashboard.
- Terraform for the core Azure resource boundary.
- Validated `dev`, `demo`, and `azure` scale/execution profiles with large-run confirmation.
- Subscription budget plus default-off Event Hubs to prevent idle streaming charges.
- GitHub Actions quality gates for Python, dbt, SQL, and Terraform.
- Python CLI for initialization, production, processing, status, and protected reset.
- Repeatable end-to-end demo and deterministic automated tests.

## Primary commands

| Goal | Command |
|---|---|
| Run full demo | `python scripts/run_demo.py` |
| Generate healthy traffic | `retailpulse produce --count 100 --scenario normal --seed 42` |
| Generate a failure | `retailpulse produce --count 60 --scenario duplicate --seed 7` |
| Inspect a scale profile | `python scripts/generate_data.py --scale dev --dry-run` |
| Run local Spark/Delta | `python spark/local_stream_bronze_silver.py` |
| Process incrementally | `retailpulse process` |
| Use Ollama when processing | `retailpulse process --ollama` |
| Inspect recent runs | `retailpulse status` |
| Build and test marts | `dbt build --project-dir dbt --profiles-dir dbt` |
| Open local dashboard | `streamlit run dashboard/app.py` |
| Start observability | `docker compose up -d prometheus node-exporter grafana` |
| Validate code | `make lint && make test` |
