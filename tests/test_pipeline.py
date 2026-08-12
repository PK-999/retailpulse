import json

from retailpulse.config import Settings
from retailpulse.incident import deterministic_report, normalize_ollama_report
from retailpulse.monitoring import evaluate, publish
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce
from retailpulse.storage import connect


def settings_for(tmp_path):
    return Settings(
        data_dir=tmp_path,
        kafka_bootstrap_servers="localhost:19092",
        kafka_enabled=False,
        ollama_url="http://localhost:11434",
        ollama_model="test",
    )


def test_pipeline_is_incremental_and_idempotent(tmp_path) -> None:
    settings = settings_for(tmp_path)
    produce(settings, 30, "normal", seed=42)
    pipeline = LocalMedallionPipeline(settings)
    first = pipeline.process()
    second = pipeline.process()

    assert first.records_read == 30
    assert first.records_written == 30
    assert second.records_read == 0
    with connect(pipeline.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM silver_events").fetchone()[0] == 30


def test_duplicate_scenario_alerts_and_generates_report(tmp_path) -> None:
    settings = settings_for(tmp_path)
    produce(settings, 30, "duplicate", seed=7)
    stats = LocalMedallionPipeline(settings).process()
    alerts = evaluate(stats)
    report = deterministic_report(stats, alerts)

    assert stats.records_duplicate == 9
    assert any(alert.metric == "duplicate_rate" for alert in alerts)
    assert "producer idempotency" in report


def test_ollama_report_normalization_removes_model_preamble() -> None:
    response = """Here is the rewritten draft:

    **Incident:** local_bronze_silver
    Evidence: duplicate_rate=26.7% in run run-123.
    Likely cause: events were replayed.
    Action: verify producer idempotency.
    """

    assert normalize_ollama_report(response) == (
        "Incident: local_bronze_silver\n"
        "Evidence: duplicate_rate=26.7% in run run-123.\n"
        "Likely cause: events were replayed.\n"
        "Action: verify producer idempotency."
    )


def test_malformed_payloads_are_quarantined(tmp_path) -> None:
    settings = settings_for(tmp_path)
    produce(settings, 20, "malformed", seed=7)
    pipeline = LocalMedallionPipeline(settings)
    stats = pipeline.process()

    assert stats.records_rejected == 5
    with connect(pipeline.database) as connection:
        quarantined = connection.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    assert quarantined == 5


def test_late_events_respect_watermark(tmp_path) -> None:
    settings = settings_for(tmp_path)
    produce(settings, 15, "late-data", seed=7)
    stats = LocalMedallionPipeline(settings).process()

    assert stats.records_late == 5
    assert any(alert.metric == "late_event_rate" for alert in evaluate(stats))


def test_gold_and_metrics_are_materialized(tmp_path) -> None:
    settings = settings_for(tmp_path)
    produce(settings, 100, "normal", seed=42)
    pipeline = LocalMedallionPipeline(settings)
    stats = pipeline.process()
    gold = pipeline.build_gold()
    publish(settings, stats, evaluate(stats))

    assert gold["orders"] > 0
    assert gold["revenue"] >= 0
    assert (tmp_path / "gold" / "summary.json").exists()
    snapshot = json.loads((tmp_path / "metrics" / "latest.json").read_text())
    assert snapshot["run"]["records_read"] == 100
