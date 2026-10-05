# Stage 6 Databricks historical batch evidence

Verification date: 2026-08-12
Status: complete

## Deployed flow

- Unscheduled Databricks job `retailpulse-stage06-historical-batch`, ID `1068750713569084`.
- One serverless notebook task in cost-efficient `STANDARD` mode, with no retry, one-run
  concurrency, and a 30-minute timeout.
- Exact `azure` profile caps: 1,000 customers, 250 products, 5,000 orders, and 25,000 order items.
- Inputs are the two immutable normalized paths produced in Stage 5, each keyed by its ADF run ID.
- Unity Catalog catalog `dbw_retailpulse_dev_rp999` with external Bronze, Silver, quarantine, and
  audit Delta tables backed by the Stage 4 external location.

## Successful deliveries

| Delivery | ADF run ID | Job run ID | Task run ID | Setup | Execution |
|---|---|---:|---:|---:|---:|
| Clean baseline | `3d93e4ea-9630-11f1-8f9b-ce7c4dd55c3a` | `353968718478960` | `405927579956295` | 185 s | 384 s |
| Incremental + invalid item | `80c5eb5c-9633-11f1-bfd1-bef4437dcc7c` | `471815232574993` | `685326230219876` | 235 s | 373 s |

Both runs ended `SUCCESS` with effective performance target `STANDARD`.

## Reconciliation

The deterministic relational subset is smaller than the configured maxima because orders and
dimensions are retained only when referenced by the selected bounded order items.

| Dataset | Clean input | Clean rejected | Injected-run rejected | Silver run 1 | Silver run 2 | Run-2 Silver writes |
|---|---:|---:|---:|---:|---:|---:|
| customers | 637 | 0 | 0 | 637 | 637 | 0 |
| products | 199 | 0 | 0 | 199 | 199 | 0 |
| orders | 1,836 | 0 | 0 | 1,836 | 1,836 | 0 |
| order_items | 4,598 | 56 | 57 of 4,599 | 4,518 | 4,518 | 0 |

The UCI source contains 56 selected return/invalid items that fail the positive-quantity rule.
The second run contains that same source-quality baseline plus exactly one deliberate item with
quantity `-1`. Valid records remained 7,214 in both runs, total quarantine rows became 113, and
the audit table contains two rows. The difference between 4,542 valid input items and 4,518 Silver
items is the intentional business-record deduplication step.

Bronze retains `source_file` from Unity Catalog `_metadata.file_path`, ingestion timestamp/date,
pipeline run ID, dataset name, and record hash. Orders use timestamp type in Silver; prices use
decimal types; null predicates are explicitly coalesced to invalid; and item quantity must be
positive with non-negative price.

## Delta and execution metrics

- First-run Delta MERGEs inserted 7,270 Bronze rows, 7,190 deduplicated Silver rows, 56 quarantine
  rows, and one audit row.
- Second-run Bronze MERGEs inserted 7,271 delivery-lineage rows. All four Silver MERGEs reported
  zero inserted, updated, deleted, output, added-file, and removed-file counts.
- Second-run quarantine inserted 57 rows and audit inserted one row, both at Delta version 2.
- Query History reported no failed statements and no spill for either successful task.
- First task: 81 statements, 1,144,272 bytes written, 14,517 rows written, 62,642 ms aggregate task
  time, and zero reported network/shuffle transfer.
- Second task: 71 statements, 796,013 bytes read, 593,662 bytes written, 7,329 rows written, 65,059
  ms aggregate task time, and zero reported network/shuffle transfer.

## Registered tables and cost closure

Unity Catalog lists all objects as external Delta tables:

- `retailpulse_bronze`: `customers`, `products`, `orders`, `order_items`.
- `retailpulse_silver`: `customers`, `products`, `orders`, `order_items`.
- `retailpulse_ops`: `historical_quarantine`, `historical_batch_runs`.

After evidence capture, active Databricks runs and classic clusters were empty, the platform starter
SQL warehouse was `STOPPED`, ADF triggers were empty, and Event Hubs namespaces remained empty.
The final Terraform refresh plan returned `No changes`.

An initial attempt failed before table writes because Unity Catalog serverless prohibits
`input_file_name()`. The notebook now uses the supported `_metadata.file_path` field and a regression
test forbids the incompatible function. A later local assertion initially assumed a perfectly clean
public workbook; cloud counts showed the 56 genuine source-quality violations, so the verifier now
requires the injected run to add exactly one rejection while leaving valid and Silver counts stable.

## Reproducible assets

- `databricks/batch_bronze_silver.py`
- `scripts/run_stage06_databricks_batch.sh`
- `tests/test_stage06_assets.py`
- `docs/runbooks/stage-06-databricks-batch.md`
