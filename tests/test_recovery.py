"""Abrupt process exits at the SQLite/export boundary, rather than simulated rollback alone."""

import json
import os
import subprocess
import sys

import pytest

from retailpulse.config import Settings
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce
from retailpulse.storage import connect, initialize_database, write_jsonl


@pytest.mark.parametrize("boundary", ["before_commit", "after_commit"])
def test_abrupt_exit_recovers_raw_classifications_offsets_and_audit(tmp_path, boundary):
    settings = Settings(tmp_path, "unused", False, "unused", "unused")
    for scenario, count in (("malformed", 20), ("late-data", 15), ("duplicate", 30)):
        produce(settings, count, scenario, seed=7)
    method = "_quarantine" if boundary == "before_commit" else "_export_classifications"
    code = f"""
import os
from retailpulse.config import Settings
from retailpulse.pipeline import LocalMedallionPipeline
pipeline = LocalMedallionPipeline(Settings.from_env())
pipeline.{method} = lambda *args: os._exit(71)
pipeline.process()
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "RETAILPULSE_DATA_DIR": str(tmp_path), "KAFKA_ENABLED": "false"},
        timeout=30,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 71, completed.stderr
    pipeline = LocalMedallionPipeline(settings)
    recovered = pipeline.process()
    assert recovered.records_read == (65 if boundary == "before_commit" else 0)
    with connect(pipeline.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM bronze_events").fetchone()[0] == 65
        assert connection.execute("SELECT COUNT(*) FROM silver_events").fetchone()[0] == 46
        assert connection.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0] == 10
        assert connection.execute("SELECT SUM(line_offset) FROM source_offsets").fetchone()[0] == 65
        status = connection.execute(
            "SELECT status FROM pipeline_run_log ORDER BY start_time LIMIT 1"
        ).fetchone()[0]
        assert status == ("INTERRUPTED" if boundary == "before_commit" else "RECOVERED")
    assert sum(len(p.read_text().splitlines()) for p in (tmp_path / "bronze").glob("*.jsonl")) == 65
    assert len((tmp_path / "quarantine" / "events.jsonl").read_text().splitlines()) == 10
    assert pipeline.process().records_read == 0


def test_legacy_raw_history_and_offsets_are_imported_once_atomically(tmp_path):
    record = {
        "source_topic": "order-events",
        "raw_payload": "broken",
        "ingestion_timestamp": "2026-10-04T00:00:00+00:00",
        "pipeline_run_id": "legacy",
    }
    bronze = tmp_path / "bronze" / "order-events.jsonl"
    write_jsonl(bronze, [record])
    with bronze.open("a") as handle:
        handle.write("bad-json\n")
    database = tmp_path / "retailpulse.db"
    with pytest.raises(ValueError):
        initialize_database(database)
    with connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM bronze_events").fetchone()[0] == 0
    write_jsonl(bronze, [record, record])
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    (checkpoints / "order-events.offset").write_text("2")
    initialize_database(database)
    initialize_database(database)
    with connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM bronze_events").fetchone()[0] == 2
        assert connection.execute("SELECT line_offset FROM source_offsets").fetchone()[0] == 2
        assert connection.execute("SELECT prefix_sha256 FROM source_offsets").fetchone()[0] is None
    assert json.loads(bronze.read_text().splitlines()[0]) == record
