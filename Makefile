.PHONY: install test lint demo up down clean

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check src tests scripts dashboard databricks spark

demo:
	python scripts/run_demo.py

up:
	docker compose up -d redpanda prometheus grafana

down:
	docker compose down

clean:
	python -m retailpulse.cli reset --yes
