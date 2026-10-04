from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text()


def test_databricks_adapter_and_secret_free_targets_are_declared() -> None:
    pyproject = read("pyproject.toml")
    profile = yaml.safe_load(read("dbt/profiles.yml"))["retailpulse"]

    assert "dbt-databricks>=1.9,<1.10" in pyproject
    assert profile["outputs"]["local"]["type"] == "duckdb"
    assert profile["outputs"]["databricks"]["type"] == "databricks"
    assert "DATABRICKS_TOKEN" in profile["outputs"]["databricks"]["token"]
    assert "DBT_ACCESS_TOKEN" in profile["outputs"]["databricks_job"]["token"]
    assert "dapi" not in read("dbt/profiles.yml").lower()


def test_cloud_sources_and_gold_incremental_models_are_wired() -> None:
    sources = read("dbt/models/sources.yml")
    assert all(
        f"name: {name}" in sources
        for name in ("customers", "products", "orders", "order_items", "streaming_events")
    )

    for model in ("fact_order_items", "fact_orders", "daily_sales"):
        sql = read(f"dbt/models/marts/{model}.sql")
        assert "materialized='incremental'" in sql
        assert "configure_gold()" in sql
        assert "is_incremental()" in sql

    assert "source('silver', 'streaming_events')" in read("dbt/models/staging/stg_events.sql")
    assert "source('silver', 'customers')" in read("dbt/models/marts/dim_customer.sql")
    assert "source('silver', 'products')" in read("dbt/models/marts/dim_product.sql")
    assert "incremental_strategy='merge'" in read("dbt/macros/configure_gold.sql")


def test_stage08_gate_and_runner_enforce_cost_and_quality_controls() -> None:
    gate = read("databricks/verify_stage08_sources.py")
    runner = read("scripts/run_stage08_dbt_gold.sh")

    assert "left_anti" in gate
    assert "historical_successes < 2" in gate
    assert "streaming_batches < 1" in gate
    assert "pause_status" in runner
    assert '"PAUSED"' in runner
    assert "stop_warehouse" in runner
    assert "DATABRICKS_TOKEN" in runner
    assert "dbt build" in runner
    assert 'commands:["dbt build"]' in runner
    assert '"${dbt_bin}" docs generate' in runner
