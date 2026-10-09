# Finish RetailPulse without additional cloud spending

Selected on 9 October 2026. Release 0.1.0 uses the verified local platform, the published
static dashboard, and clearly dated historical Azure evidence. A fresh Azure run is optional
future work, rather than a gate for this portfolio release.

## 1. Use the local environment

Start at the root of your checkout. For a new checkout:

```bash
git clone https://github.com/PK-999/retailpulse.git
cd retailpulse
```

Create a local environment with Python 3.11–3.13. Substitute `python3.12` or `python3.13`
below if needed:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,analytics,dashboard]'
python --version
```

The checkpoint is an active Python 3.11–3.13 environment with those dependencies installed.
An existing checkout can reuse a supported environment. On the original workstation, activate
the installed Python 3.13.15 environment with `source .venv313/bin/activate`; its old `.venv`
uses unsupported Python 3.14. The remaining commands run from the checkout root.

This route uses local files, SQLite, DuckDB, and deterministic incident analysis. It needs
neither Azure credentials nor a hosted model. Leave the expired trial unupgraded for this route;
Azure stage runners and Terraform apply are outside its scope.

## 2. Reproduce the complete flow

```bash
python scripts/run_local_e2e.py \
  --work-dir data/portfolio-final \
  --output data/portfolio-final/proof.json
```

The work directory must be new. Choose another name when repeating the demonstration; the
runner refuses an existing directory so it can preserve previous results.

The checkpoint is:

| Check | Expected result |
|---|---|
| Classification | 295 Bronze = 266 Silver + 19 duplicates + 10 quarantine |
| Gold | 10 orders, 57 units, £268.55 |
| dbt | 37 nodes pass in each clean, incremental, and full-refresh build |
| Replay | An unchanged ingestion rerun reads zero input |
| Analytics correctness | Unchanged incremental results match the full refresh |
| Operations | Duplicate, malformed, and late scenarios produce their respective DQ alerts |

The [9 October local proof](evidence/zero-cost-local-e2e.json) records a fresh successful run.
Its incident report uses deterministic rules. Earlier integration evidence covers
[Spark/Delta and Kafka](evidence/local-spark-contract.md),
[Prometheus/Grafana](evidence/local-monitoring.json), and
[Ollama incident analysis](evidence/stage-01-ollama-report.md), with each artifact's original scope.
The 9 October finish additionally passed ten orchestration/recovery/dashboard tests and all
17 BI/Streamlit browser tests at desktop and mobile widths. The public snapshot still matches
the committed archive byte for byte.

## 3. Show the local business and operational results

```bash
RETAILPULSE_DATA_DIR=data/portfolio-final streamlit run dashboard/app.py \
  --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open the displayed local URL. Show revenue, orders, business dates, commerce charts, inventory,
and pipeline runs. Explain quarantine and replay using `proof.json` and the files under the
same demo directory. Stop this terminal with Ctrl+C after presenting.

## 4. Show the published portfolio

Open the [public dashboard](https://pk-999.github.io/retailpulse/) and the
[5-minute walkthrough](portfolio-walkthrough.md). Visit Overview, Commerce, and Freshness.

The public dashboard contains the Azure Gold export from **15 August 2026** for business dates
**2010–2011**. Its £91,970.02 and 1,796 orders belong to that archive, while the local proof above
uses synthetic events. Preserve the archive's original export time; it is not a live Azure feed.
Viewing the site and recording uses the saved artifacts and starts no Azure compute.

For a local static preview, with the frontend dependencies installed:

```bash
npm --prefix bi-dashboard run build
npm --prefix bi-dashboard run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

## 5. Present the engineering evidence

Use the [architecture](architecture.md), [project status](project-status.md),
[release checklist](release-checklist.md), and saved evidence to explain contracts, immutable
Bronze, quarantine, idempotent MERGE, checkpoints, transactional recovery, incremental dbt,
SCD Type 2 history, monitoring, and CI.

Suggested portfolio description:

> Built a retail data platform with batch and streaming ingestion, Bronze/Silver/Gold layers,
> event contracts, quarantine and replay recovery, incremental dbt marts, SCD2 history, and
> operational dashboards. Verified the current implementation locally with automated tests;
> retained historical Azure integration evidence and published a static Azure Gold dashboard.

State the boundary: the refactored deployment has not been rerun on Azure, and cloud monitoring
delivery remains unverified. The [Azure execution plan](execution-plan.md) remains available
for a separately funded future validation session.

## 6. Close the portfolio release

Retain the proof, walkthrough, screenshots, public snapshot, source code, and CI results in GitHub.
Close local preview/dashboard terminals after the demonstration. Local verification does not
depend on the expired Azure subscription.

The portal warning supplied on 9 October says the expired trial will be deleted on **11 October
2026**. These repository artifacts remain available independently; they are not a backup of
the Azure lake or remote Terraform state. Data-plane/state access is disabled, so cloud backup,
teardown, and future billing status have not been verified. This route creates no additional
Azure resources or workload usage; it does not make a claim about an existing account's balance.

The zero-additional-cloud-cost finish line is a reproducible local demonstration, accessible
portfolio artifacts, and accurate verification scope. Paid Azure execution and its teardown
stay outside this release.
