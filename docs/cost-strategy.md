# RetailPulse cost and execution strategy

Last reviewed: 2026-08-12

## Decision

Develop and rehearse the data logic locally. Use Databricks Free Edition only as an optional,
non-commercial notebook practice environment. Use paid Azure Databricks solely for the bounded
Event Hubs → Databricks → ADLS integration proof and final recording.

Free Edition is not Azure integration evidence: it is serverless-only, quota-limited, has no SLA,
and does not support custom workspace storage locations. The portfolio claim therefore remains
backed by a short run in the provisioned Azure workspace.

## Environment boundaries

| Profile | Purpose | Default compute | Dataset scale | Spend boundary |
|---|---|---|---|---|
| `dev` | Daily Kafka/Spark/Delta/dbt development | Local machine | 10K customers, 2K products, 100K orders, 500K events | No cloud compute |
| `demo` | Local performance rehearsal | Local machine; Free Edition optional | 100K customers, 10K products, 1M orders, 5M events | No paid Azure compute |
| `azure` | Integration and evidence capture | Databricks job compute | 1K customers, 250 products, 5K orders, 25K events | 30-minute maximum run |

The versioned settings are in `config/dev.yml`, `config/demo.yml`, and `config/azure.yml`.
Profile cardinalities define the generated identifier domains. A large generation requires an
explicit `--yes` confirmation:

```bash
python scripts/generate_data.py --scale dev --dry-run
python scripts/generate_data.py --scale dev --yes
```

## Enforced controls

- Terraform defaults `enable_event_hubs=false`. Enable it only in the reviewed Stage 7 plan and
  disable it immediately after streaming evidence is captured.
- The Azure budget covers the subscription, including state and Databricks-managed resource
  groups. Alerts notify; they are not a hard spending cap.
- Terraform creates no Databricks cluster or SQL warehouse.
- Azure execution uses job or serverless-job compute. An all-purpose cluster requires a documented
  exception and a 10-minute automatic termination setting.
- Structured Streaming defaults to `AvailableNow`, caps offsets per trigger, and uses a distinct
  checkpoint namespace. Processing-time mode stops after at most 30 minutes.
- The Azure dataset is a connectivity/recovery proof, not the performance dataset. Larger tests run
  against local Spark/Delta or, where appropriate, Free Edition default storage.
- Gold facts and daily sales are incremental dbt models keyed by order item, order, and date.
- Every Azure session ends by stopping compute, checking cost analysis, and following the teardown
  decision in the execution plan.

## Spark optimization rules

- Select only required columns and filter input before joins or writes.
- Never use `collect()` on a large DataFrame; bounded single-row inspection must be explicit.
- Broadcast genuinely small dimensions and record why they qualify.
- Repartition only for a measured reason; avoid high-cardinality Delta partitions.
- Use event IDs or business keys for idempotent MERGE, with source-side deduplication.
- Process new deliveries and changed dates/orders instead of rebuilding the full history.
- Record input rows, output rows, shuffle/read bytes, duration, and Delta operation metrics before
  describing an optimization as successful.

## Evidence required before cost claims

Cost and performance statements must record profile, runtime, worker/DBU configuration, wall-clock
duration, processed rows, and the Azure Cost Management time window. Estimates remain estimates
until matched to an actual billable run.

## Primary references

- [Azure Databricks Free Edition limitations](https://learn.microsoft.com/en-us/azure/databricks/getting-started/free-edition-limitations)
- [Azure Databricks Structured Streaming triggers](https://learn.microsoft.com/en-us/azure/databricks/structured-streaming/triggers)
- [Azure Databricks jobs compute](https://learn.microsoft.com/en-us/azure/databricks/jobs/compute)
- [Delta Lake and Spark compatibility](https://docs.delta.io/releases/)
- [Apache Spark downloads and releases](https://spark.apache.org/downloads/)
