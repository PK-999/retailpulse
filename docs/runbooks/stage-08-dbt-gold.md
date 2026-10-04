# Stage 8 dbt-on-Databricks Gold runbook

## Purpose

Build tested Azure Gold relations from the Stage 6 historical and Stage 7 streaming Silver tables,
prove incremental and SCD2 behavior, and deploy a disabled-by-default production-shaped workflow.

## Prerequisites

- Stages 3–7 are complete and the Terraform state is reachable.
- Docker Desktop is running for the pinned Azure CLI/Terraform wrappers.
- A Python 3.11–3.13 environment contains the `analytics` and `databricks` extras. The default
  runner path is `.venv/bin/dbt`; override it with `RETAILPULSE_DBT_BIN` if needed.
- The current Git branch exists in the public GitHub repository before enabling the deployed job.

If tenant security blocks Azure CLI device-code flow with `AADSTS530035`, use the supported local
browser flow while sharing the repository credential cache:

```bash
AZURE_CONFIG_DIR="$PWD/.azure" az login \
  --tenant 96f9afec-6ab2-4896-81d4-d19f597dc039 \
  --subscription 6545f282-9a08-4115-b6f1-10c590d3fc7f
```

## Run

```bash
./scripts/run_stage08_dbt_gold.sh
```

The runner:

1. verifies non-empty Silver relations plus Stage 6/7 audit evidence;
2. obtains a short-lived Azure Databricks token without persisting it;
3. runs `dbt debug`, `compile`, and two `build` passes;
4. reconciles customer, product, item, and revenue totals;
5. proves zero-source Delta MERGEs for the three incremental models;
6. changes one product price, snapshots it, restores the price, and snapshots the restoration;
7. reruns all tests and generates dbt documentation artifacts; and
8. creates or resets the freshness-gated weekly job in `PAUSED` state.

An exit trap restores the price if needed, clears the token, and stops the SQL warehouse on both
success and failure.

## Success gate

- Both dbt builds pass all 37 nodes and the final 26-test pass is green.
- Silver/Gold customers, products, items, and revenue match exactly.
- `fact_order_items`, `fact_orders`, and `daily_sales` each report a zero-source MERGE.
- The selected product has at least two SCD2 versions and exactly one current row.
- The source price is restored, the deployed workflow is paused, the warehouse is stopped, and
  Terraform reports no changes.
