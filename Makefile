PYTHON ?= python
DEMO_DIR ?= data/portfolio-demo

.PHONY: help install demo dashboard e2e test lint verify dbt bi up down clean

help:
	@printf '%s\n' \
	  'make install    Install Python demo and validation dependencies' \
	  'make demo       Run the complete demo in a NEW directory and keep its proof' \
	  'make dashboard  Open Streamlit using the same demo directory' \
	  'make e2e        Run the complete flow in temporary storage' \
	  'make verify     Run Python, SQL and frontend checks' \
	  'make bi         Install and build the archived snapshot dashboard' \
	  'make up/down    Start/stop local Kafka and monitoring services' \
	  'make clean      Delete the selected demo directory' \
	  'Set PYTHON and DEMO_DIR to select an interpreter or another demo directory.'

install:
	$(PYTHON) -m pip install -e '.[dev,analytics,dashboard,databricks]'

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests scripts dashboard databricks spark

demo:
	$(PYTHON) scripts/run_local_e2e.py --work-dir "$(DEMO_DIR)" --output "$(DEMO_DIR)/proof.json"

dashboard:
	RETAILPULSE_DATA_DIR="$(DEMO_DIR)" $(PYTHON) -m streamlit run dashboard/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false

e2e:
	$(PYTHON) scripts/run_local_e2e.py

verify: lint test
	$(PYTHON) -m sqlfluff lint dbt/models dbt/tests --templater jinja
	npm --prefix bi-dashboard ci
	npm --prefix bi-dashboard run lint
	npm --prefix bi-dashboard test

dbt:
	RETAILPULSE_DBT_DATA_DIR="$(DEMO_DIR)" RETAILPULSE_DBT_PATH="$(DEMO_DIR)/gold/warehouse.duckdb" \
	  $(PYTHON) -c 'from dbt.cli.main import cli; cli()' build --project-dir dbt --profiles-dir dbt --target local

bi:
	npm --prefix bi-dashboard ci
	npm --prefix bi-dashboard run lint
	npm --prefix bi-dashboard run build

up:
	RETAILPULSE_DATA_DIR="$(abspath $(DEMO_DIR))" docker compose up -d redpanda prometheus node-exporter grafana

down:
	RETAILPULSE_DATA_DIR="$(abspath $(DEMO_DIR))" docker compose down

clean:
	RETAILPULSE_DATA_DIR="$(DEMO_DIR)" $(PYTHON) -m retailpulse.cli reset --yes
