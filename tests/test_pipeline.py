import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from retailpulse.config import Settings
from retailpulse.events import EventGenerator
from retailpulse.incident import deterministic_report, normalize_ollama_report
from retailpulse.monitoring import evaluate, publish
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce
from retailpulse.storage import append_raw, connect


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


def test_failed_processing_does_not_skip_rolled_back_events(tmp_path, monkeypatch) -> None:
    settings = settings_for(tmp_path)
    append_raw(
        tmp_path / "inbox" / "customer-events.jsonl",
        json.dumps(
            {
                "event_id": str(uuid4()),
                "event_type": "search",
                "query": "gift",
                "event_timestamp": datetime.now(UTC).isoformat(),
                "schema_version": 1,
            }
        ),
    )
    append_raw(tmp_path / "inbox" / "order-events.jsonl", "broken")
    pipeline = LocalMedallionPipeline(settings)

    with monkeypatch.context() as patch:

        def unavailable_quarantine(*args):
            raise OSError("Quarantine storage unavailable")

        patch.setattr(pipeline, "_quarantine", unavailable_quarantine)
        with pytest.raises(OSError, match="Quarantine storage"):
            pipeline.process()

    recovered = pipeline.process()
    assert recovered.records_written == 1
    assert recovered.records_rejected == 1
    with connect(pipeline.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM silver_events").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT status FROM pipeline_run_log ORDER BY start_time"
            ).fetchone()[0]
            == "FAILED"
        )
    exported = [
        json.loads(line) for line in (tmp_path / "silver" / "events.jsonl").read_text().splitlines()
    ]
    assert len(exported) == 1
    assert exported[0]["query"] == "gift"


def test_events_on_wrong_topic_are_quarantined(tmp_path) -> None:
    settings = settings_for(tmp_path)
    message = next(EventGenerator(seed=42).generate(1))
    assert message.topic == "order-events"
    append_raw(tmp_path / "inbox" / "customer-events.jsonl", message.payload)
    pipeline = LocalMedallionPipeline(settings)
    stats = pipeline.process()
    assert stats.records_written == 0
    assert stats.records_rejected == 1
    with connect(pipeline.database) as connection:
        assert (
            connection.execute("SELECT error_type FROM quarantine").fetchone()[0]
            == "TOPIC_MISMATCH"
        )


def test_checkpoint_write_failure_recovers_committed_input_without_replay(
    tmp_path, monkeypatch
) -> None:
    settings = settings_for(tmp_path)
    produce(settings, 30, "normal", seed=42)
    pipeline = LocalMedallionPipeline(settings)

    with monkeypatch.context() as patch:

        def failed_checkpoint(*args):
            raise OSError("Checkpoint unavailable")

        patch.setattr(pipeline, "_save_offset", failed_checkpoint)
        with pytest.raises(OSError, match="Checkpoint unavailable"):
            pipeline.process()

    recovered = pipeline.process()
    assert recovered.records_read == 0
    assert recovered.records_written == 0
    assert recovered.records_duplicate == 0
    assert len((tmp_path / "silver" / "events.jsonl").read_text().splitlines()) == 30


def test_failed_transaction_does_not_export_uncommitted_classifications(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    produce(settings, 20, "malformed", seed=7)
    pipeline = LocalMedallionPipeline(settings)
    original = pipeline._quarantine

    def fail_after_insert(*args):
        original(*args)
        raise OSError("Interrupted classification")

    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "_quarantine", fail_after_insert)
        with pytest.raises(OSError, match="Interrupted classification"):
            pipeline.process()
    pipeline.process()
    assert len((tmp_path / "quarantine" / "events.jsonl").read_text().splitlines()) == 5
    assert (
        sum(len(path.read_text().splitlines()) for path in (tmp_path / "bronze").glob("*.jsonl"))
        == 20
    )


@pytest.mark.parametrize("replacement", ["", "different\n"])
def test_changed_or_truncated_committed_source_is_detected(tmp_path, replacement):
    settings = settings_for(tmp_path)
    produce(settings, 20, "normal", seed=7)
    pipeline = LocalMedallionPipeline(settings)
    pipeline.process()
    source = tmp_path / "inbox" / "order-events.jsonl"
    source.write_text(replacement)
    with pytest.raises(ValueError, match="changed|truncated"):
        pipeline.process()


@pytest.mark.parametrize("price", ["1.005", "0.145", "0.1234567890123456789012345"])
def test_silver_preserves_decimal_prices_as_text(tmp_path, price) -> None:
    append_raw(
        tmp_path / "inbox" / "order-events.jsonl",
        json.dumps(
            {
                "event_id": str(uuid4()),
                "event_type": "purchase",
                "order_id": "O1",
                "product_id": "P1",
                "quantity": 2,
                "price": price,
                "event_timestamp": datetime.now(UTC).isoformat(),
                "schema_version": 1,
            }
        ),
    )
    LocalMedallionPipeline(settings_for(tmp_path)).process()
    exported = json.loads((tmp_path / "silver" / "events.jsonl").read_text())
    assert exported["price"] == price
    gold = LocalMedallionPipeline(settings_for(tmp_path)).build_gold()
    expected = {"1.005": 2.02, "0.145": 0.30, "0.1234567890123456789012345": 0.24}
    assert gold["revenue"] == expected[price]


def test_unrepresentable_gold_price_keeps_committed_silver_and_previous_marts(tmp_path):
    settings = settings_for(tmp_path)
    produce(settings, 100, "normal", seed=42)
    pipeline = LocalMedallionPipeline(settings)
    pipeline.process()
    previous = pipeline.build_gold()
    record = {
        "event_id": str(uuid4()),
        "event_type": "purchase",
        "order_id": "big-order",
        "product_id": "P1",
        "quantity": 1,
        "price": "9999999999.995",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "schema_version": 1,
    }
    append_raw(tmp_path / "inbox" / "order-events.jsonl", json.dumps(record))
    assert pipeline.process().records_written == 1
    with pytest.raises(ValueError, match="Gold unit price exceeds"):
        pipeline.build_gold()
    with connect(pipeline.database) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0]
            == previous["orders"]
        )
        assert (
            connection.execute(
                "SELECT price FROM silver_events WHERE order_id='big-order'"
            ).fetchone()[0]
            == "9999999999.995"
        )
