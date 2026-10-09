# RetailPulse cost and execution strategy

Release scope reviewed: 2026-10-09; original Azure cost estimates are dated below.

The selected finish is the [zero-additional-cloud-cost local portfolio release](zero-cost-finish.md).
Use the current local proof, published static snapshot, and recorded walkthrough. Subscription
upgrade, Azure stage execution, cloud alert deployment, and a fresh cloud recording are deferred.
The historical Azure exception and optional execution modes below do not authorize new spending.

October 2026 operational update: the exception below expired 2026-08-19. A read-only review
sees disabled ADF and `AccountIsDisabled` on Terraform state storage; it did not execute paid
jobs or apply changes. Restore service access and review a new bounded plan before cloud work.
Optional monitoring now defaults off and adds one metric alert, with existing-storage log
archive and explicitly authorized receivers only when selected; see
[Stage 10](runbooks/stage-10-cloud-monitoring.md). No Log Analytics workspace is introduced.

## Decision

Develop, verify, and present the data logic locally for this release. Databricks Free Edition
remains an optional non-commercial notebook practice environment. A future paid Azure Databricks
session would be limited to a separately authorized Event Hubs → Databricks → ADLS integration
proof and recording.

Free Edition is not Azure integration evidence: it is serverless-only, quota-limited, has no SLA,
and does not support custom workspace storage locations. The portfolio claim therefore remains
backed by the saved August Azure run, with its historical scope made explicit. The refactored
deployment has not been rerun on Azure.

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
- Terraform defaults `enable_databricks_workspace=false`. A workspace using Databricks' managed
  VNet and secure cluster connectivity creates a managed NAT gateway and public IP that can accrue
  hourly charges even when no cluster is running. Enable the workspace only for bounded setup,
  integration, and recording sessions, then remove it while retaining ADLS, ADF, Key Vault, and
  the Access Connector.
- The Azure budget covers the subscription, including state and Databricks-managed resource
  groups. Alerts notify; they are not a hard spending cap.
- Terraform creates no Databricks cluster or SQL warehouse. A workspace alone is not cost-free
  because Azure creates its managed networking outside the explicit Terraform resource list.
- The Azure workspace uses Premium solely for Unity Catalog compatibility; no DBUs are consumed
  until compute runs.
- Azure execution uses job or serverless-job compute. An all-purpose cluster requires a documented
  exception and a 10-minute automatic termination setting.
- Structured Streaming defaults to `AvailableNow`, caps offsets per trigger, and uses a distinct
  checkpoint namespace. Processing-time mode stops after at most 30 minutes.
- The Azure dataset is a connectivity/recovery proof, not the performance dataset. Larger tests run
  against local Spark/Delta or, where appropriate, Free Edition default storage.
- Gold facts and daily sales are incremental dbt models keyed by order item, order, and date.
- Every Azure session ends by stopping compute, checking cost analysis, and following the teardown
  decision in the execution plan.

## Deployment modes

### Zero Azure resource cost

Run account inspection, provider registration, Terraform formatting, `init -backend=false`, and
validation only. Do not bootstrap remote state and do not run `terraform apply`. This proves the
configuration structure but does not prove Azure deployment.

### Minimal-cost Azure proof

Use an ignored `terraform/dev.tfvars` with a USD 10 budget, `enable_event_hubs=false`, and
`enable_databricks_workspace=false` for the parked baseline. Bootstrap remote state, create a
saved plan, and reject it if it contains Event Hubs, Databricks compute, SQL warehouses, VMs, or
Log Analytics. A plan that creates the Databricks workspace does not enumerate the NAT gateway and
public IP that Azure creates in its locked managed resource group; account for them separately.

Set `enable_databricks_workspace=true` only on a demonstration day. Apply, complete the bounded
Databricks work, capture evidence, return the flag to `false`, review the destroy-only workspace
plan, and apply it promptly. Never delete resources directly from the Databricks-managed resource
group.

### Current Stage 4 exception

On 2026-08-12 the operator elected to keep the workspace available through the tagged
`2026-08-19` teardown date because the subscription has USD 200 of free credit. The August 2026
retail estimate for the idle managed network is USD 0.045/hour for the Standard NAT gateway plus
USD 0.005/hour for its Standard static IPv4: approximately USD 0.05/hour, USD 1.20/day, or USD
8.40 for seven complete days. Data processing, storage, transactions, and any compute are extra.

This is a time-bounded exception, not a claim that an idle workspace is free. Event Hubs remains
disabled and no Databricks cluster or SQL warehouse may be left running. The prepared workspace
cost-pause plan remains available if actual Cost Analysis or remaining credit makes early teardown
necessary.

Immediately after apply, verify that Event Hubs and Databricks compute are absent, ADF has no
active triggers or runs, Cost Analysis is scoped to the subscription, and the budget exists.
Budgets alert but do not stop charges.

An actual deployment cannot be guaranteed to cost exactly zero. Storage capacity/transactions,
Key Vault operations, ADF operations, and (while the workspace exists) Databricks-managed storage
and networking can generate charges even when workload compute is stopped.

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
- [Azure Databricks Unity Catalog setup requirements](https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/setup-uc)
- [Managed identities for Unity Catalog storage](https://learn.microsoft.com/en-us/azure/databricks/connect/unity-catalog/cloud-storage/azure-managed-identities)
- [Secure cluster connectivity and managed-VNet NAT cost](https://learn.microsoft.com/en-us/azure/databricks/security/network/classic/secure-cluster-connectivity#egress-with-default-managed-vnet)
- [Azure NAT Gateway pricing](https://azure.microsoft.com/en-us/pricing/details/azure-nat-gateway/)
- [Azure public IP pricing](https://azure.microsoft.com/en-us/pricing/details/ip-addresses/)
- [Delta Lake and Spark compatibility](https://docs.delta.io/releases/)
- [Apache Spark downloads and releases](https://spark.apache.org/downloads/)
