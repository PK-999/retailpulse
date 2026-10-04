from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SILVER_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS silver_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        customer_id TEXT,
        product_id TEXT,
        order_id TEXT,
        quantity INTEGER,
        price TEXT,
        country TEXT,
        event_timestamp TEXT NOT NULL,
        ingestion_timestamp TEXT NOT NULL,
        source_topic TEXT NOT NULL,
        pipeline_run_id TEXT NOT NULL,
        query TEXT
    );
"""


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")


def append_raw(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload.rstrip("\n") + "\n")


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    """Replace an exported snapshot only after every record has been written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        try:
            for record in records:
                handle.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_text(path: Path, content: str) -> None:
    """Atomically publish a text/JSON/metrics file without exposing partial content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def connect(database: Path) -> Iterator[sqlite3.Connection]:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database(database: Path) -> None:
    with connect(database) as connection:
        connection.executescript(
            SILVER_TABLE_SQL
            + """
            CREATE TABLE IF NOT EXISTS quarantine (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                raw_payload TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_offsets (
                source_topic TEXT PRIMARY KEY,
                line_offset INTEGER NOT NULL CHECK(line_offset >= 0),
                prefix_sha256 TEXT
            );
            CREATE TABLE IF NOT EXISTS bronze_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_topic TEXT NOT NULL,
                source_offset INTEGER,
                raw_payload TEXT NOT NULL,
                ingestion_timestamp TEXT NOT NULL,
                pipeline_run_id TEXT NOT NULL,
                UNIQUE(source_topic, source_offset)
            );
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS pipeline_run_log (
                run_id TEXT PRIMARY KEY,
                pipeline_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT NOT NULL,
                records_read INTEGER NOT NULL,
                records_written INTEGER NOT NULL,
                records_rejected INTEGER NOT NULL,
                records_duplicate INTEGER NOT NULL,
                records_late INTEGER NOT NULL,
                duration_seconds REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fact_orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT,
                order_timestamp TEXT NOT NULL,
                country TEXT,
                units INTEGER NOT NULL,
                order_total REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS daily_sales (
                order_date TEXT PRIMARY KEY,
                orders INTEGER NOT NULL,
                units INTEGER NOT NULL,
                revenue REAL NOT NULL,
                average_order_value REAL NOT NULL
            );
            """
        )
        _upgrade_silver(connection, database)
        _upgrade_local_state(connection, database)


def _upgrade_local_state(connection: sqlite3.Connection, database: Path) -> None:
    """Import prior raw history/checkpoints once; subsequent exports come only from SQLite."""
    migration = "transactional-input-v1"
    if connection.execute(
        "SELECT 1 FROM schema_migrations WHERE name = ?", (migration,)
    ).fetchone():
        return
    if not connection.in_transaction:
        connection.execute("BEGIN")
    for path in sorted((database.parent / "bronze").glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                connection.execute(
                    """INSERT INTO bronze_events
                       (source_topic, raw_payload, ingestion_timestamp, pipeline_run_id)
                       VALUES (?, ?, ?, ?)""",
                    (
                        record["source_topic"],
                        record["raw_payload"],
                        record["ingestion_timestamp"],
                        record["pipeline_run_id"],
                    ),
                )
    for path in sorted((database.parent / "checkpoints").glob("*.offset")):
        offset = int(path.read_text(encoding="utf-8").strip())
        connection.execute(
            "INSERT INTO source_offsets (source_topic, line_offset) VALUES (?, ?)",
            (path.stem, offset),
        )
    connection.execute("INSERT INTO schema_migrations VALUES (?)", (migration,))


def _upgrade_silver(connection: sqlite3.Connection, database: Path) -> None:
    """Preserve committed legacy rows and recover exact prices/queries from their export."""
    columns = {
        row["name"]: row["type"] for row in connection.execute("PRAGMA table_info(silver_events)")
    }
    missing_query = "query" not in columns
    numeric_price = columns.get("price") == "REAL"
    if not missing_query and not numeric_price:
        return
    # sqlite3 starts transactions for DML, so explicitly include migration DDL too.
    connection.execute("BEGIN")
    if missing_query:
        connection.execute("ALTER TABLE silver_events ADD COLUMN query TEXT")
    if numeric_price:
        connection.execute("ALTER TABLE silver_events RENAME TO silver_events_legacy")
        connection.execute(SILVER_TABLE_SQL)
        connection.execute(
            """INSERT INTO silver_events
               SELECT event_id, event_type, customer_id, product_id, order_id, quantity,
                      CAST(price AS TEXT), country, event_timestamp, ingestion_timestamp,
                      source_topic, pipeline_run_id, query
               FROM silver_events_legacy"""
        )
        connection.execute("DROP TABLE silver_events_legacy")
    legacy_export = database.parent / "silver" / "events.jsonl"
    if legacy_export.exists():
        with legacy_export.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("query") is not None:
                    connection.execute(
                        "UPDATE silver_events SET query = ? WHERE event_id = ?",
                        (record["query"], record["event_id"]),
                    )
                if numeric_price and record.get("price") is not None:
                    connection.execute(
                        "UPDATE silver_events SET price = ? WHERE event_id = ?",
                        (str(record["price"]), record["event_id"]),
                    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
