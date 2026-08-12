from pathlib import Path

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "databricks" / "stream_bronze_silver.py"
VERIFIER = ROOT / "databricks" / "verify_stage07.py"
RUNNER = ROOT / "scripts" / "run_stage07_eventhubs_streaming.sh"
TERRAFORM = ROOT / "terraform" / "main.tf"


def test_stage07_notebook_uses_secret_backed_event_hubs_authentication() -> None:
    notebook = NOTEBOOK.read_text(encoding="utf-8")

    assert "dbutils.secrets.get(scope=secret_scope, key=secret_key)" in notebook
    assert 'option("kafka.security.protocol", "SASL_SSL")' in notebook
    assert 'option("kafka.sasl.mechanism", "PLAIN")' in notebook
    assert 'option("kafka.sasl.jaas.config", sasl_jaas)' in notebook
    assert "kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule" in notebook
    assert "SharedAccess" + "Key=" not in notebook
    assert "connection_string" not in RUNNER.read_text(encoding="utf-8").split(
        'notebook_params:{', maxsplit=1
    )[1].split("}", maxsplit=1)[0]


def test_stage07_notebook_has_idempotent_delta_quality_and_metrics() -> None:
    notebook = NOTEBOOK.read_text(encoding="utf-8")

    assert "retailpulse_bronze" in notebook
    assert "retailpulse_silver" in notebook
    assert "streaming_quarantine" in notebook
    assert "streaming_batch_runs" in notebook
    assert "target.stream_run_id = source.stream_run_id" in notebook
    assert "target.event_id = source.event_id" in notebook
    assert "WHEN NOT MATCHED THEN INSERT *" in notebook
    assert '.withWatermark("watermark_event_timestamp", "30 minutes")' in notebook
    assert "average_latency_ms" in notebook
    assert "processed_rows_per_second" in notebook
    assert "DESCRIBE HISTORY" in notebook


def test_stage07_recovery_fault_occurs_after_merges_and_reuses_checkpoint() -> None:
    notebook = NOTEBOOK.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    fault_index = notebook.index("STAGE7_INTENTIONAL_FAILURE_AFTER_COMMITTED_BATCH")
    assert notebook.index("bronze_history = merge_frame") < fault_index
    assert notebook.index("silver_history = merge_frame") < fault_index
    assert notebook.index("audit_table,\n        audit_path") < fault_index
    assert 'run_stream available_now true earliest INTENTIONAL_FAILURE' in runner
    assert 'run_stream available_now false earliest SUCCESS' in runner
    assert "checkpoint_namespace" in runner
    assert "numTargetRowsInserted" in runner
    assert 'trigger(processingTime=' not in notebook
    assert '"audit_results": audit_results' in notebook
    assert '.filter(F.col("checkpoint_namespace") == checkpoint_namespace)' in notebook


def test_stage07_runner_enforces_temporary_cost_and_secret_cleanup() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    terraform = TERRAFORM.read_text(encoding="utf-8")

    assert "validate_event_hubs_plan" in runner
    assert 'expected_count}" == "exact"' in runner
    assert "changed_count > 4" in runner
    assert "azurerm_eventhub_namespace" in runner
    assert "azurerm_eventhub" in runner
    assert "trap cleanup EXIT" in runner
    assert "trap 'exit 130' INT" in runner
    assert "trap 'exit 143' TERM" in runner
    assert "eventhubs namespace authorization-rule create" in runner
    assert "--rights Listen Send" in runner
    assert "/api/2.0/secrets/scopes/delete" in runner
    assert "keyvault secret delete" in runner
    assert "-var=enable_event_hubs=false" in runner
    assert "Event Hubs namespace still exists" in runner
    assert "authorization_rule" not in terraform


def test_stage07_runner_covers_all_scenarios_and_reconciliation() -> None:
    runner = RUNNER.read_text(encoding="utf-8")

    for scenario in (
        "normal",
        "duplicate",
        "late-data",
        "malformed",
        "traffic-spike",
        "checkpoint-recovery",
    ):
        assert f"produce_scenario {scenario}" in runner
    assert ".bronze_total == 460" in runner
    assert ".silver_total == 411" in runner
    assert ".silver_unique_event_ids == 411" in runner
    assert ".quarantine_total == 30" in runner


def test_stage07_durable_verifier_asserts_replay_and_scenario_counts() -> None:
    verifier = VERIFIER.read_text(encoding="utf-8")

    assert '"status": "STAGE7_DURABLE_EVIDENCE_VERIFIED"' in verifier
    assert 'recovery["records_read"] == 40' in verifier
    assert 'recovery["bronze_history"].get("numTargetRowsInserted", -1)' in verifier
    assert 'recovery["silver_history"].get("numTargetRowsInserted", -1)' in verifier
    assert 'summary["bronze_total"] == 460' in verifier
    assert 'summary["silver_unique_event_ids"] == 411' in verifier
    assert 'summary["transport_metadata_nulls"] == 0' in verifier
