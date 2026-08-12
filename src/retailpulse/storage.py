from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")


def append_raw(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload.rstrip("\n") + "\n")


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
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS silver_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                customer_id TEXT,
                product_id TEXT,
                order_id TEXT,
                quantity INTEGER,
                price REAL,
                country TEXT,
                event_timestamp TEXT NOT NULL,
                ingestion_timestamp TEXT NOT NULL,
                source_topic TEXT NOT NULL,
                pipeline_run_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quarantine (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                raw_payload TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                timestamp TEXT NOT NULL
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


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
