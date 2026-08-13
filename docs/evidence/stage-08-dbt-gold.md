# Stage 8 dbt-on-Databricks Gold evidence

Verification date: 2026-08-13
Status: complete

## Runtime and security boundary

- Python 3.13.15, dbt Core 1.9.10, dbt-databricks 1.9.8.
- Serverless SQL warehouse `74d4ebde2c184d68`; explicitly stopped after verification.
- Unity Catalog `dbw_retailpulse_dev_rp999`, target schema `retailpulse_gold`.
- Gold data is stored as external Delta under the existing ADLS `gold/dbt` boundary.
- The checked-in profiles contain environment-variable references only. The attended runner used
  a short-lived Azure Databricks token and removed it from the process environment on exit.

## Build and reconciliation

`dbt debug` and `dbt compile` passed. Both live `dbt build` runs passed all 37 nodes: 10 models,
one snapshot, and 26 data tests.

| Measure | Silver | Gold |
|---|---:|---:|
| Customers | 637 | 637 |
| Products | 199 | 199 |
| Order items | 4,518 | 4,518 |
| Revenue | £91,970.02 | £91,970.02 |
| Daily-sales revenue | — | £91,970.02 |

The second build recorded Delta `MERGE` with `numSourceRows=0`, `numOutputRows=0`, no inserted or
updated rows, and no added or removed files for `fact_order_items`, `fact_orders`, and
`daily_sales`. This proves the unchanged run filters changed keys/dates instead of rebuilding the
incremental tables.

## SCD2 proof

Product `10002` was changed from `0.00` to `1.00`, `dim_product` was rebuilt, and the snapshot
created a second version with one current row. The source was then restored to `0.00` and
snapshotted again. Final verification returned three historical versions, exactly one current row,
and matching source/current-snapshot price `0.00`.

## Documentation and scheduling

- `dbt docs generate` produced `manifest.json`, `catalog.json`, and the lineage site in the ignored
  `dbt/target` build directory.
- Paused workflow `retailpulse-stage08-dbt-gold`, job ID `611598520636749`.
- The first task is a serverless Silver readiness gate; the dbt task runs only after it succeeds.
- The weekly Monday 09:00 Asia/Kolkata schedule is deliberately `PAUSED` to avoid unattended cost.

## Operational closure

- SQL warehouse: `STOPPED`.
- Active Databricks runs: zero.
- Classic clusters: zero.
- Event Hubs remains disabled from Stage 7.
- Final Terraform refresh plan: `No changes`.

The initial live attempt exposed a Databricks SQL dialect difference: this warehouse requires
`STRING` rather than an unbounded `VARCHAR` cast. The cloud branch now uses `STRING`; the local
DuckDB branch retains `VARCHAR`. The failed attempt did not reach the SCD2 mutation, and its cleanup
trap stopped the warehouse.
