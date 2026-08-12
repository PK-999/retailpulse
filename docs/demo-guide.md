# RetailPulse demo guide

## 1. Local prerequisites

- Python 3.11–3.13; Python 3.11 is recommended.
- Docker Desktop for broker, monitoring, dashboard container, or Ollama demonstrations.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,analytics]'
```

## 2. Fast deterministic demonstration

```bash
python scripts/run_demo.py
```

Expected sequence:

1. 100 normal events reach Silver.
2. Gold order and revenue values are materialized.
3. Duplicate traffic pushes the duplicate rate above 5%.
4. A DQ alert and incident report identify event replay/idempotency as the likely cause.

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

```bash
dbt build --project-dir dbt --profiles-dir dbt
streamlit run dashboard/app.py
```

Show revenue, orders, average order value, conversion rate, top countries/products/customers,
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
ruff check src tests scripts dashboard
pytest
sqlfluff lint dbt/models dbt/tests --templater jinja
docker compose config -q
```

For the Azure recording, also capture a reviewed Terraform plan, successful ADF run, Databricks
job output, Delta table history, dbt lineage, live monitoring alert, and the final incident report.
