# RetailPulse demo guide

## 1. Local prerequisites

- Python 3.11–3.13; Python 3.11 is recommended.
- Docker Desktop for broker, monitoring, dashboard container, or Ollama demonstrations.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,analytics,dashboard]'
```

## 2. Fast deterministic demonstration

For the complete, isolated release proof:

```bash
make e2e
# Keep artifacts only in a NEW directory:
python scripts/run_local_e2e.py --work-dir data/portfolio-demo --output /tmp/proof.json
```

Expected:295 Bronze,266 Silver,19 duplicates,10 quarantined,10 orders,57 units,£268.55;
all 37 dbt nodes pass clean, incremental, and full-refresh builds. The runner checks unchanged
reruns and Gold reconciliation. Default temporary runs leave existing data alone. Use
`RETAILPULSE_DATA_DIR=data/portfolio-demo` for subsequent CLI/Streamlit commands.

For the shorter four-step example:

```bash
python scripts/run_demo.py
```

Expected sequence:

1. 100 normal events reach Silver.
2. Gold order and revenue values are materialized.
3. Duplicate traffic pushes the duplicate rate above 5%.
4. A DQ alert and incident report identify event replay/idempotency as the likely cause.

Gold is refreshed after the duplicate batch too. A fresh run ends with 141 unique Silver events,
10 orders, 32 units, and £145.18 revenue. The demo always uses file-backed transport.
It appends to existing data; select a new `RETAILPULSE_DATA_DIR` for an isolated walkthrough.

Inspect:

```text
data/bronze/
data/silver/events.jsonl
data/quarantine/events.jsonl
data/gold/summary.json
data/metrics/latest.json
data/incidents/
```

## 3. Scenario-by-scenario demonstration

```bash
retailpulse init
retailpulse produce --count 100 --scenario normal --seed 42
retailpulse process
retailpulse status
```

Then choose one failure:

```bash
retailpulse produce --count 60 --scenario duplicate --seed 7
retailpulse produce --count 60 --scenario late-data --seed 7
retailpulse produce --count 60 --scenario malformed --seed 7
retailpulse produce --count 60 --scenario traffic-spike --seed 7
retailpulse process
```

Run only one scenario between processing commands when demonstrating its isolated effect.

## 4. Analytics and dashboard

For the Azure-backed portfolio view:

```bash
make bi
npm --prefix bi-dashboard run dev
```

Show the archived Azure snapshot badge, business window and export time, revenue/orders/AOV/purchase-view ratio,
daily and country sales, products/customers, inventory state, event pulse, and five-of-five
reconciliation strip. This uses the committed snapshot and needs no Azure credentials.
For an attended cloud refresh, install `.[databricks]` and follow the Stage 9 runbook.
The refresh runner stops the SQL warehouse when it exits. For the public
version, use the `Deploy BI Lite` GitHub Pages workflow after reviewing the committed snapshot.

For the deterministic local view:

```bash
dbt build --project-dir dbt --profiles-dir dbt
streamlit run dashboard/app.py
```

Show revenue, orders, average order value, purchase/view ratio, top countries/products/customers,
event volume per minute, inventory freshness, pipeline runs, and active alerts.

## 5. Monitoring

```bash
docker compose up -d prometheus node-exporter grafana
```

- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`
- Default Grafana credentials: `admin` / `retailpulse`

Run another processing scenario after starting monitoring so the textfile metrics contain current
run values.

## 6. Optional Ollama analysis

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull llama3.2:3b
retailpulse process --ollama
```

If Ollama is unavailable, the command retains a deterministic incident report and identifies the
source as `rules-fallback`.

## 7. Validation before recording

```bash
pip install -e '.[dev,analytics,dashboard,databricks]'
ruff check src tests scripts dashboard spark databricks
python -m pytest
sqlfluff lint dbt/models dbt/tests --templater jinja
docker compose config -q
npm --prefix bi-dashboard ci
npm --prefix bi-dashboard run lint
npm --prefix bi-dashboard run build
npx --prefix bi-dashboard playwright install chromium
npm --prefix bi-dashboard test
```

For the Azure recording, also capture a reviewed Terraform plan, successful ADF run, Databricks
job output, Delta table history, dbt lineage, live monitoring alert, and the final incident report.
This sequence currently waits for Azure access restoration; the [read-only preflight](evidence/cloud-monitor-preflight.json)
reports ADF disabled. Local checks and August cloud evidence have separate scopes.
