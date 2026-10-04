import json
import sqlite3
import stat

import pytest

from retailpulse.storage import connect, initialize_database, write_jsonl, write_text


@pytest.mark.parametrize("writer", [write_text, write_jsonl])
def test_derived_exports_remain_readable_by_dashboard_and_metrics_container_users(tmp_path, writer):
    output = tmp_path / "export"
    output.write_text("old")
    output.chmod(0o600)
    writer(output, "metrics\n" if writer is write_text else [{"event_id": "committed"}])
    assert stat.S_IMODE(output.stat().st_mode) == 0o644


def test_failed_snapshot_preserves_previous_export(tmp_path) -> None:
    output = tmp_path / "events.jsonl"
    write_jsonl(output, [{"event_id": "committed"}])

    def failing_records():
        yield {"event_id": "uncommitted"}
        raise OSError("Read failed")

    with pytest.raises(OSError, match="Read failed"):
        write_jsonl(output, failing_records())
    assert json.loads(output.read_text()) == {"event_id": "committed"}
    assert list(tmp_path.iterdir()) == [output]


def test_database_upgrade_keeps_existing_silver(tmp_path) -> None:
    database = tmp_path / "retailpulse.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE silver_events (event_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO silver_events VALUES ('existing')")
    initialize_database(database)
    with connect(database) as connection:
        row = connection.execute("SELECT event_id, query FROM silver_events").fetchone()
    assert tuple(row) == ("existing", None)


def test_database_upgrade_preserves_queries_from_legacy_export(tmp_path) -> None:
    database = tmp_path / "retailpulse.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE silver_events (event_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO silver_events VALUES ('existing')")
    write_jsonl(
        tmp_path / "silver" / "events.jsonl",
        [
            {"event_id": "existing", "query": "gift"},
            {"event_id": "uncommitted", "query": "other"},
        ],
    )
    initialize_database(database)
    with connect(database) as connection:
        rows = connection.execute("SELECT event_id, query FROM silver_events").fetchall()
    assert [tuple(row) for row in rows] == [("existing", "gift")]


def test_failed_database_upgrade_can_be_retried(tmp_path) -> None:
    database = tmp_path / "retailpulse.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE silver_events (event_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO silver_events VALUES ('existing')")
    export = tmp_path / "silver" / "events.jsonl"
    export.parent.mkdir()
    export.write_text("broken")
    with pytest.raises(ValueError):
        initialize_database(database)
    write_jsonl(export, [{"event_id": "existing", "query": "gift"}])
    initialize_database(database)
    with connect(database) as connection:
        row = connection.execute("SELECT event_id, query FROM silver_events").fetchone()
    assert tuple(row) == ("existing", "gift")


def test_legacy_real_prices_recover_original_decimal_text(tmp_path) -> None:
    database = tmp_path / "retailpulse.db"
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE silver_events (
            event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
            customer_id TEXT, product_id TEXT, order_id TEXT, quantity INTEGER,
            price REAL, country TEXT, event_timestamp TEXT NOT NULL,
            ingestion_timestamp TEXT NOT NULL, source_topic TEXT NOT NULL,
            pipeline_run_id TEXT NOT NULL
        )""")
        connection.execute("""INSERT INTO silver_events VALUES (
            'existing', 'purchase', 'C1', 'P1', 'O1', 1, 0.123456789012345678,
            'UK', '2026-10-04', '2026-10-04', 'order-events', 'legacy'
        )""")
    write_jsonl(
        tmp_path / "silver" / "events.jsonl",
        [
            {
                "event_id": "existing",
                "query": None,
                "price": "0.123456789012345678",
            }
        ],
    )
    initialize_database(database)
    initialize_database(database)
    with connect(database) as connection:
        row = connection.execute("SELECT price, typeof(price) FROM silver_events").fetchone()
    assert tuple(row) == ("0.123456789012345678", "text")
