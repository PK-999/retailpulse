# Stage 9 RetailPulse BI Lite runbook

## Purpose

Refresh the public dashboard from Azure Gold, validate its trust indicators, build the static site,
and confirm Databricks compute is stopped. Refresh is an attended, billable operation; it is not
part of browser visits or routine local verification.

The current Azure subscription is disabled. Keep reviewing the archived public snapshot locally;
resume the attended refresh only after the subscription and warehouse are available.

## Prerequisites

- Stage 8 Gold tables and dbt tests are complete.
- The attended operator is signed into the selected Azure subscription.
- A Python 3.11–3.13 `.venv` contains the `databricks` extra. Override
  `RETAILPULSE_PYTHON_BIN` when using another supported environment.
- Node.js and npm are available; Playwright Chromium is installed for browser verification.
- `curl`, `jq`, and Bash are available for the attended runner.
- The serverless starter SQL warehouse exists; it may begin in `STOPPED` state.

## Authentication

The runner first uses an already exported `DATABRICKS_TOKEN`. If none is present, it requests a
short-lived Microsoft Entra token from the repository's Azure CLI session. Prefer the short-lived
Azure CLI path when tenant policy permits it. If local Azure CLI sign-in is blocked (for example,
`AADSTS530035` on an unmanaged device), create a short-lived workspace personal access token in
**Databricks > user menu > Settings > Developer > Access tokens > Manage**, if token creation is
enabled for the workspace.

Keep local values in the ignored `.env.local` file:

```bash
cp .env.example .env.local
chmod 600 .env.local
```

Edit `.env.local` and set `DATABRICKS_TOKEN` to the newly generated token. Do not include quotes or
spaces around the value. Then load it only into the current shell:

```bash
set -a
source .env.local
set +a
```

The user or service principal represented by the credential needs Databricks SQL access, `CAN USE`
or stronger on warehouse `74d4ebde2c184d68`, and `USE CATALOG`, `USE SCHEMA`, and `SELECT` on the
RetailPulse catalog objects. Stopping the warehouse through the API requires warehouse ownership
or `CAN MANAGE`; the existing project operator is the warehouse owner.

## Refresh and build

```bash
./scripts/run_stage09_bi_dashboard.sh
```

The runner explicitly starts warehouse `74d4ebde2c184d68`, waits up to ten minutes for `RUNNING`
(including any initial `STOPPING` state), executes query version `stage09-v2`, checks five
Silver/Gold invariants and dashboard KPI/daily totals, atomically replaces
`bi-dashboard/public/data/dashboard.json`, and runs frontend lint/build.

Cleanup retries the stop request up to three times and polls until `STOPPED`, with a default
three-minute limit. Individual API calls have ten-second connection and thirty-second request
caps. Override `RETAILPULSE_WAREHOUSE_START_TIMEOUT_SECONDS` or
`RETAILPULSE_WAREHOUSE_STOP_TIMEOUT_SECONDS` only when necessary; each must be at least 30 seconds.

Successful startup is explicit in the terminal:

```text
SQL warehouse 74d4ebde2c184d68 is RUNNING.
```

`STAGE9_SNAPSHOT_VERIFIED` proves that SQL executed and the snapshot checks passed. A successful
attended run also ends with **`SQL warehouse 74d4ebde2c184d68 confirmed STOPPED.`** and exit code zero.

Cleanup runs after success, failure, and handled INT/TERM signals. If it cannot confirm `STOPPED`,
it prints a warning and turns an otherwise successful run into exit code 1. When extraction/build
already failed, cleanup preserves that original failure code and prints a separate warning.
Inspect the SQL warehouse immediately after a cleanup warning; automatic stop is a secondary
control and must not be treated as proof of stopped compute.

To check the final state without printing the token, use the workspace UI under **SQL Warehouses**.
It should move from `RUNNING` during refresh to `STOPPED` after the runner exits. You can also use
the Azure-authenticated CLI path:

```bash
AZURE_CONFIG_DIR="$PWD/.azure" az rest \
  --method get \
  --url "https://${RETAILPULSE_DATABRICKS_HOST}/api/2.0/sql/warehouses/${RETAILPULSE_DATABRICKS_WAREHOUSE_ID}" \
  --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d \
  --query state -o tsv
```

Do not publish a hand-edited JSON file as verified evidence. A snapshot is publishable only when
its metadata status is `verified`, its query version is known, and all reconciliation checks pass.

## Local review

```bash
npm --prefix bi-dashboard run dev
```

Open the Vite URL under `/retailpulse/`. The snapshot-age notice describes time since export;
the reporting window describes historic business dates. Inventory status and five-of-five
reconciliation refer to export time. Purchase/view ratio compares independently sampled stream
counts and is not customer conversion.

Run the reproducible production-browser checks from the repository root:

```bash
npm --prefix bi-dashboard ci
npm --prefix bi-dashboard exec -- playwright install chromium
npm --prefix bi-dashboard run lint
npm --prefix bi-dashboard test
npm --prefix bi-dashboard run test:evidence
.venv313/bin/python -m pytest tests/test_dashboard.py tests/test_stage09_assets.py
```

`test:evidence` writes all three views at 1440px and 390px to `docs/assets/bi-dashboard/`.
If a compatible Chromium is already installed, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its
executable path instead of downloading another browser. The browser suite covers keyboard
navigation, console/page errors, horizontal overflow, malformed JSON, retry, empty data, and age
semantics.

The local Streamlit dashboard remains a separate operational demo:

```bash
KAFKA_ENABLED=false RETAILPULSE_DATA_DIR=/tmp/retailpulse-demo .venv313/bin/retailpulse produce --count 100 --scenario normal --seed 42
RETAILPULSE_DATA_DIR=/tmp/retailpulse-demo .venv313/bin/retailpulse process --no-ollama
RETAILPULSE_DATA_DIR=/tmp/retailpulse-demo .venv313/bin/streamlit run dashboard/app.py --server.address 127.0.0.1
```

With that server running, capture its desktop/narrow evidence:

```bash
RETAILPULSE_STREAMLIT_URL=http://127.0.0.1:8501 RETAILPULSE_CAPTURE_EVIDENCE=1 npm --prefix bi-dashboard run test:browser -- local-dashboard.spec.ts
```

The local chart rounds unit prices to pennies before multiplying quantities, matching local
Gold. Missing databases, unreadable marts, and malformed monitoring JSON have explicit UI states.
See the [portfolio walkthrough](../portfolio-walkthrough.md) for a recording script.

## Publish

The `Deploy BI Lite` GitHub Actions workflow builds only committed static assets. It does not
possess Azure or Databricks credentials and cannot refresh data. After reviewing the JSON diff,
commit the snapshot and web changes to `main`, enable GitHub Pages with **GitHub Actions** as the
source, and run the workflow.

## Cost and incident controls

- A browser request cannot contact or start Databricks.
- The runner confirms `STOPPED` after successful and failed refreshes. Failure to confirm is
  visible and produces a nonzero exit; the operator must inspect the warehouse.
- A workspace token is held only in the attended shell environment; `.env.local` is ignored by Git.
- If reconciliation fails, retain the prior public snapshot and investigate Stage 8 before retrying.
- Exports older than 24 hours display an archived notice. Business dates remain separate; do not
  hide freshness by editing metadata.
- Never add tokens, workspace bearer headers, raw payloads, email addresses, or connection strings
  to public assets.
