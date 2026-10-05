from pathlib import Path

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "databricks" / "batch_bronze_silver.py"
RUNNER = ROOT / "scripts" / "run_stage06_databricks_batch.sh"


def test_stage06_notebook_enforces_bounded_profile_and_delivery_lineage() -> None:
    notebook = NOTEBOOK.read_text(encoding="utf-8")

    assert 'profile_name != "azure"' in notebook
    assert "(1000, 250, 5000, 25000)" in notebook
    assert "pipeline_run_id not in landing_path" in notebook
    assert 'F.to_timestamp("order_timestamp", "yyyy-MM-dd HH:mm:ss")' in notebook
    assert 'withColumn("pipeline_run_id"' in notebook
    assert 'F.col("_metadata.file_path").alias("source_file")' in notebook
    assert "input_file_name" not in notebook
    assert 'withColumn("ingestion_timestamp"' in notebook


def test_stage06_creates_named_external_tables_and_idempotent_merges() -> None:
    notebook = NOTEBOOK.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS" in notebook
    assert "USING DELTA LOCATION" in notebook
    assert "retailpulse_bronze" in notebook
    assert "retailpulse_silver" in notebook
    assert "historical_quarantine" in notebook
    assert "historical_batch_runs" in notebook
    assert "WHEN MATCHED AND target._record_hash <> source._record_hash" in notebook
    assert "WHEN NOT MATCHED THEN INSERT *" in notebook
    assert 'table_name.replace("`", "").split(".")[-1]' in notebook


def test_stage06_injects_invalid_item_and_records_delta_metrics() -> None:
    notebook = NOTEBOOK.read_text(encoding="utf-8")

    assert "STAGE06-INVALID" in notebook
    assert 'Decimal("1.00")' in notebook
    assert "F.coalesce(valid_conditions[name], F.lit(False))" in notebook
    assert "quantity > 0" in notebook
    assert "DESCRIBE HISTORY" in notebook
    assert '"records_rejected"' in notebook
    assert "delta_metrics_json STRING" in notebook


def test_stage06_runner_compares_injected_row_to_source_quality_baseline() -> None:
    runner = RUNNER.read_text(encoding="utf-8")

    assert "second_rejected != first_rejected + 1" in runner
    assert "The injected invalid row unexpectedly changed the valid-record count" in runner
    assert "Silver ${dataset} changed across the identical valid delivery" in runner
    assert "The injected rejection was not isolated to order_items" in runner
