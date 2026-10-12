# Run and present RetailPulse

This is the canonical demo guide. It reproduces the complete local platform without additional
Azure spending. The public dashboard and recorded walkthrough use saved artifacts.

## 1. Prepare a checkout

```bash
git clone https://github.com/PK-999/retailpulse.git
cd retailpulse
python3.11 -m venv .venv
source .venv/bin/activate
make install
```

Python 3.11–3.13 is supported. Substitute `python3.12` or `python3.13` when creating the
environment. An existing checkout can reuse a supported environment. On the original workstation,
`source .venv313/bin/activate` selects Python 3.13.15; its old `.venv` uses unsupported Python 3.14.
Environment variables are documented in [`.env.example`](../.env.example); the Python application
does not automatically load `.env` files.

## 2. Run the complete demonstration

```bash
make demo
```

This runs the single [end-to-end runner](../scripts/run_local_e2e.py), retains artifacts under
`data/portfolio-demo/`, and writes `proof.json` there. It generates normal, duplicate, malformed,
late, and spike traffic, processes it, builds SQLite Gold, and runs dbt clean/incremental/full-refresh.

| Checkpoint | Expected |
|---|---|
| Classification | 295 Bronze = 266 Silver + 19 duplicates + 10 quarantine |
| Gold | 10 orders, 57 units, £268.55 |
| dbt | 37 passing nodes per build; unchanged rerun and full-refresh equivalence |
| Quality | Duplicate, rejection, and lateness alerts in the scenario evidence |
| Incidents | Deterministic duplicate-incident report; no model dependency |

An existing demo directory is preserved. Choose a new name to rerun:

```bash
make demo DEMO_DIR=data/another-demo
make dashboard DEMO_DIR=data/another-demo
```

Use the same `DEMO_DIR` for all subsequent Make commands. `make e2e` performs the complete
flow in temporary storage when retained dashboard data is unnecessary. `PYTHON=/path/to/python`
selects an interpreter explicitly.

## 3. Show the local dashboard

```bash
make dashboard
```

Open `http://localhost:8501`. Show commerce totals, dated local data, products/customers,
inventory freshness, and pipeline audit rows. Stop the server with Ctrl+C when finished.
Streamlit reads SQLite Gold; dbt independently builds and tests the corresponding DuckDB marts.

Inspect the same demo directory:

| Artifact | Meaning |
|---|---|
| `bronze/` | Original input retained for replay |
| `silver/events.jsonl` | Validated, deduplicated event export |
| `quarantine/events.jsonl` | Rejected/late payloads and reasons |
| `retailpulse.db` | Transactional local data and audit ledger |
| `gold/summary.json`, `gold/warehouse.duckdb` | SQLite summary and dbt analytics |
| `metrics/`, `incidents/`, `proof.json` | Operational outputs and aggregate verification |

## 4. Demonstrate a quality incident

Select the demo data explicitly for CLI commands:

```bash
export RETAILPULSE_DATA_DIR="$PWD/data/portfolio-demo"
export KAFKA_ENABLED=false
retailpulse produce --count 60 --scenario duplicate --seed 7
retailpulse process
retailpulse status
```

Processing preserves duplicate Bronze inputs, inserts only unique Silver IDs, updates Gold,
records an audit, and emits a quality alert and incident report. This additional scenario changes
the live dashboard totals; `proof.json` records the earlier baseline.

For live monitoring, Docker Desktop is optional:

```bash
make up
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin / retailpulse)
```

Monitoring mounts the selected `DEMO_DIR/metrics`, matching the demo and dashboard. Process
another scenario after starting it to demonstrate alert firing. [Saved operations evidence](evidence/local-monitoring.json)
also records firing and recovery. `make down` stops the local Compose services.

Ollama is optional: `retailpulse process --ollama` tries the configured local model and falls
back to deterministic rules. An already installed model is sufficient; it is not required for
this demonstration.

## 5. Present the portfolio

Open the [public dashboard](https://pk-999.github.io/retailpulse/) and
[5-minute walkthrough](portfolio-walkthrough.md). Explain contracts, quarantine, replay recovery,
incremental models, SCD2 history, monitoring, and CI using the [architecture](architecture.md)
and [verification evidence](evidence/README.md).

The public React application displays an Azure Gold export from **15 August 2026**, covering
**2010–2011**, with **£91,970.02 / 1,796 orders**. These are archived historical figures,
separate from the synthetic local demo. Page views use static assets and start no Azure compute.

For a local static preview, Node.js 24 is required:

```bash
make bi
npm --prefix bi-dashboard run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

Suggested portfolio description:

> Built a retail data platform with batch and streaming ingestion, Bronze/Silver/Gold layers,
> strict event contracts, quarantine and replay recovery, incremental dbt marts, SCD2 history,
> and operational dashboards. Verified the current implementation locally; retained dated Azure
> integration evidence and published a static Azure Gold dashboard.

## 6. Verify and close

Run `make verify` after installing Playwright Chromium as shown in the README. Spark/Delta and
Terraform have separate CI jobs; the [evidence index](evidence/README.md) records their scope.
Stop local dashboard/preview terminals and use `make down` after monitoring. `make clean` deletes
only the selected demo directory, so retain any proof you want first.

Fresh Azure deployment, cloud alert delivery, and target-service cleanup remain deferred.
Use the [optional Azure plan](execution-plan.md) only for a separately authorized cloud session.
Repository source, proof, screenshots, and the recording remain independent of the expired Azure
trial; they are not a backup of its lake or remote Terraform state.
