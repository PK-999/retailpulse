.PHONY: install test lint demo e2e verify dbt bi up down clean

install:
	python -m pip install -e '.[dev,analytics,dashboard]'

test:
	python -m pytest

lint:
	ruff check src tests scripts dashboard databricks spark

demo:
	python scripts/run_demo.py

e2e:
	python scripts/run_local_e2e.py

verify: lint test
	sqlfluff lint dbt/models dbt/tests --templater jinja
	npm --prefix bi-dashboard ci
	npm --prefix bi-dashboard run lint
	npm --prefix bi-dashboard test

dbt:
	dbt build --project-dir dbt --profiles-dir dbt

bi:
	npm --prefix bi-dashboard ci
	npm --prefix bi-dashboard run lint
	npm --prefix bi-dashboard run build

up:
	docker compose up -d redpanda prometheus node-exporter grafana

down:
	docker compose down

clean:
	python -m retailpulse.cli reset --yes
