# Stage 1 local external-service verification

Verification date: 2026-08-12

## Result

Stage 1 is functionally verified. Redpanda/Kafka, Prometheus, rendered Grafana QA, Streamlit
behavior, and both Ollama execution paths passed. The stage exit gate remains open only for
refreshed desktop and narrow-width Streamlit screenshots because no in-app browser was attached
during the closure run.

## 1A — Redpanda/Kafka

- Redpanda reported healthy with no leaderless or under-replicated partitions.
- `customer-events`, `order-events`, and `inventory-events` were created with three partitions
  each.
- A seeded 30-event run delivered successfully through `localhost:19092`.
- One schema-version-1 JSON event was consumed from each topic.
- Partition high-watermarks reconciled to the producer count: 19 customer, 10 order, and 1
  inventory event.
- The broker was stopped and started; its topics remained available afterward.

Result: passed.

## 1B — Prometheus and Grafana

- `prometheus`, `node-exporter`, and `grafana` started successfully.
- Prometheus reported both active targets as `up`: `redpanda:9644` and
  `node-exporter:9100` (`job=retailpulse`).
- Healthy run `4f6714d9-b69a-4bca-98e0-9fd2e1545793` read and wrote 100 records with no alerts.
- Duplicate run `031adb03-493c-44a4-b303-1337691a6071` read 60 records, wrote 41, detected 19
  duplicates, and raised one alert.
- Prometheus returned `retailpulse_duplicate_rate=0.31666666666666665` and
  `retailpulse_alerts=1` for the degraded run.
- Grafana 11.1.3 reported its database healthy and provisioned dashboard UID
  `retailpulse-ops` with panels for records read, duplicate rate, rejection rate, active alerts,
  and pipeline duration.

Result: passed. The user-provided rendered dashboard screenshot shows all five panels without
clipping and reconciles to the degraded run: 15 records, 26.7% duplicates, 0% rejected, and one
active alert.

## 1C — Streamlit

- The app health endpoint returned `ok` at `http://127.0.0.1:8501`.
- Streamlit's application test runner completed with zero exceptions and found five top-level
  metrics and all seven expected data sections.
- The verified snapshot showed revenue £346.68, 27 orders, £12.84 AOV, 94 product views, and a
  31.9% conversion rate.
- A clean data directory produced the intended instruction message, zero metrics, and zero
  exceptions.
- Deprecated chart/table width arguments were replaced and regression-tested.
- Desktop visual QA found that a single-day revenue series looked empty as a line chart. The app
  now renders a bar for a one-day series and retains a line for multi-day series.

Result: functional and empty-state checks passed. The supplied desktop screenshot has no clipping
or unreadable labels; a refreshed screenshot is needed to confirm the single-day revenue fix.
Narrow-width visual QA is pending.

## 1D — Ollama

- Ollama 0.3.6 downloaded and loaded `llama3.2:3b` from its persistent Docker volume.
- Duplicate run `2ddc5eca-6819-436b-98dd-c06746aa1f29` produced a normalized model report with
  the measured 26.7% duplicate rate, exact run ID, grounded likely cause, and approved action.
- With Ollama stopped, duplicate run `0cf0a335-bcde-4262-b066-aefba0928cf1` completed immediately
  with source `rules-fallback` and the same class of deterministic remediation.
- Both reports align with the [duplicate-events runbook](../runbooks/duplicate-events.md): retain
  event-ID deduplication and verify producer idempotence before replay.
- Ollama was restarted after the fallback test.

Evidence reports:

- [Model-backed incident report](stage-01-ollama-report.md)
- [Rules fallback incident report](stage-01-rules-fallback-report.md)

Result: passed.

## Regression checks

- Ruff: passed.
- Pytest: 18 passed.
- Streamlit populated-state test: zero exceptions.
- Streamlit empty-state test: zero exceptions.
- Single-day revenue visualization: Vega-Lite bar mark asserted.
- Live Streamlit health endpoint: `ok`.

## Visual evidence follow-up

`STG1-VIS-001` was open when this evidence was captured. It is resolved in the October release:
desktop and narrow Streamlit browser checks pass, screenshots are retained, and the same cases
pass against the non-root Docker image with read-only data. See
[current dashboard evidence](stage-09-bi-dashboard.md) and
[release verification](release-verification.json).
