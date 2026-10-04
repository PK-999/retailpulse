import json
import os
import subprocess
import sys

from retailpulse.storage import connect
from scripts.run_demo import main


def test_demo_help_does_not_generate_or_modify_data(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/run_demo.py", "--help"],
        env={**os.environ, "RETAILPULSE_DATA_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "demonstration" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_demo_reconciles_gold_after_all_batches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))
    main()
    with connect(tmp_path / "retailpulse.db") as connection:
        purchases = connection.execute(
            "SELECT SUM(quantity), ROUND(SUM(quantity * price), 2) "
            "FROM silver_events WHERE event_type = 'purchase'"
        ).fetchone()
        orders = connection.execute(
            "SELECT SUM(units), ROUND(SUM(order_total), 2) FROM fact_orders"
        ).fetchone()
    assert tuple(orders) == tuple(purchases)
    summary = json.loads((tmp_path / "gold" / "summary.json").read_text())
    assert summary["revenue"] == purchases[1]


def test_demo_uses_local_transport_with_kafka_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RETAILPULSE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAFKA_ENABLED", "true")

    def unavailable_kafka(*args):
        raise AssertionError("The local demo must work without a broker")

    monkeypatch.setattr("retailpulse.producer.KafkaSink", unavailable_kafka)
    main()
    with connect(tmp_path / "retailpulse.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM silver_events").fetchone()[0] == 141
