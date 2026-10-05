from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from retailpulse.config import Settings
from retailpulse.contracts import TOPIC_BY_EVENT, QuarantineRecord, RetailEvent
from retailpulse.storage import connect, initialize_database, utc_now, write_jsonl, write_text


@dataclass
class RunStats:
    run_id: str
    pipeline_name: str
    start_time: str
    end_time: str = ""
    status: str = "RUNNING"
    records_read: int = 0
    records_written: int = 0
    records_rejected: int = 0
    records_duplicate: int = 0
    records_late: int = 0
    duration_seconds: float = 0.0

    @property
    def duplicate_rate(self) -> float:
        return self.records_duplicate / self.records_read if self.records_read else 0.0

    @property
    def rejection_rate(self) -> float:
        return self.records_rejected / self.records_read if self.records_read else 0.0


class LocalMedallionPipeline:
    """Deterministic local equivalent of the Databricks streaming transformation.

    Input offsets, raw records, and classifications commit together in SQLite. JSONL
    exports/checkpoint files are replaceable materializations repaired on the next run.
    """

    watermark = timedelta(minutes=30)

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_directories()
        self.database = settings.data_dir / "retailpulse.db"
        initialize_database(self.database)
        self.last_stats: RunStats | None = None

    def _checkpoint(self, topic: str) -> Path:
        return self.settings.data_dir / "checkpoints" / f"{topic}.offset"

    def _offset(self, connection: sqlite3.Connection, topic: str) -> tuple[int, str | None]:
        row = connection.execute(
            "SELECT line_offset, prefix_sha256 FROM source_offsets WHERE source_topic = ?",
            (topic,),
        ).fetchone()
        return (row["line_offset"], row["prefix_sha256"]) if row else (0, None)

    def _save_offset(self, topic: str, offset: int) -> None:
        write_text(self._checkpoint(topic), str(offset))

    def _quarantine(
        self, connection: sqlite3.Connection, raw: str, error_type: str, message: str
    ) -> None:
        event_id = None
        with suppress(json.JSONDecodeError, AttributeError):
            event_id = str(json.loads(raw).get("event_id") or "") or None
        record = QuarantineRecord(
            event_id=event_id, raw_payload=raw, error_type=error_type, error_message=message
        )
        connection.execute(
            """INSERT INTO quarantine
               (event_id, raw_payload, error_type, error_message, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (
                record.event_id,
                record.raw_payload,
                record.error_type,
                record.error_message,
                record.timestamp.isoformat(),
            ),
        )

    def process(self) -> RunStats:
        started = time.monotonic()
        now = datetime.now(UTC)
        stats = RunStats(
            run_id=str(uuid4()), pipeline_name="local_bronze_silver", start_time=now.isoformat()
        )
        self.last_stats = stats
        self._write_audit(stats)
        offsets: dict[str, int] = {}
        try:
            with connect(self.database) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """UPDATE pipeline_run_log SET status = 'INTERRUPTED', end_time = ?
                       WHERE status = 'RUNNING' AND run_id != ?""",
                    (utc_now(), stats.run_id),
                )
                for topic in dict.fromkeys(TOPIC_BY_EVENT.values()):
                    source = self.settings.data_dir / "inbox" / f"{topic}.jsonl"
                    offset, prefix = self._offset(connection, topic)
                    if not source.exists():
                        if offset:
                            raise ValueError(f"Committed source {topic} is missing or truncated")
                        continue
                    with source.open(encoding="utf-8") as handle:
                        offsets[topic], digest = self._process_topic(
                            connection, handle, topic, offset, prefix, now, stats
                        )
                    connection.execute(
                        """INSERT INTO source_offsets VALUES (?, ?, ?)
                           ON CONFLICT(source_topic) DO UPDATE SET
                           line_offset = excluded.line_offset,
                           prefix_sha256 = excluded.prefix_sha256""",
                        (topic, offsets[topic], digest),
                    )
                stats.status = "COMMITTED"
                self._store_audit(connection, stats)
            self._export_classifications()
            with connect(self.database) as connection:
                connection.execute(
                    """UPDATE pipeline_run_log SET status = 'RECOVERED', end_time = ?
                       WHERE status = 'COMMITTED' AND run_id != ?""",
                    (utc_now(), stats.run_id),
                )
            for topic, offset in offsets.items():
                self._save_offset(topic, offset)
            stats.status = "SUCCESS"
        except Exception:
            stats.status = "FAILED"
            raise
        finally:
            stats.end_time = utc_now()
            stats.duration_seconds = round(time.monotonic() - started, 6)
            self._write_audit(stats)
        return stats

    def _export_classifications(self) -> None:
        with connect(self.database) as connection:
            for topic in dict.fromkeys(TOPIC_BY_EVENT.values()):
                rows = connection.execute(
                    """SELECT raw_payload, source_topic, ingestion_timestamp, pipeline_run_id
                       FROM bronze_events WHERE source_topic = ? ORDER BY id""",
                    (topic,),
                )
                write_jsonl(
                    self.settings.data_dir / "bronze" / f"{topic}.jsonl",
                    (dict(row) for row in rows),
                )
            for name, query in (
                ("silver", "SELECT *, 1 AS schema_version FROM silver_events ORDER BY rowid"),
                ("quarantine", "SELECT * FROM quarantine ORDER BY id"),
            ):
                rows = connection.execute(query)
                write_jsonl(
                    self.settings.data_dir / name / "events.jsonl", (dict(row) for row in rows)
                )

    def _process_topic(
        self,
        connection: sqlite3.Connection,
        lines: Iterable[str],
        topic: str,
        offset: int,
        prefix: str | None,
        now: datetime,
        stats: RunStats,
    ) -> tuple[int, str]:
        line_count = 0
        digest = hashlib.sha256()
        for line_count, line in enumerate(lines, start=1):
            raw = line.rstrip("\r\n")
            digest.update((raw + "\n").encode("utf-8"))
            if line_count <= offset:
                if line_count == offset and prefix is not None and digest.hexdigest() != prefix:
                    raise ValueError(f"Committed source prefix changed for {topic}")
                continue
            stats.records_read += 1
            ingestion_timestamp = utc_now()
            connection.execute(
                """INSERT INTO bronze_events
                   (source_topic, source_offset, raw_payload, ingestion_timestamp, pipeline_run_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (topic, line_count, raw, ingestion_timestamp, stats.run_id),
            )
            try:
                event = RetailEvent.model_validate_json(raw)
            except (ValidationError, ValueError) as error:
                stats.records_rejected += 1
                self._quarantine(connection, raw, "SCHEMA_VALIDATION", str(error))
                continue
            event_id = str(event.event_id)
            if TOPIC_BY_EVENT[event.event_type] != topic:
                stats.records_rejected += 1
                self._quarantine(
                    connection,
                    raw,
                    "TOPIC_MISMATCH",
                    f"{event.event_type} must use {TOPIC_BY_EVENT[event.event_type]}",
                )
                continue
            exists = connection.execute(
                "SELECT 1 FROM silver_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if exists:
                stats.records_duplicate += 1
                continue
            if event.event_timestamp < now - self.watermark:
                stats.records_late += 1
                self._quarantine(
                    connection,
                    raw,
                    "LATE_EVENT",
                    "event_timestamp is older than the 30-minute watermark",
                )
                continue
            values = (
                event_id,
                event.event_type,
                event.customer_id,
                event.product_id,
                event.order_id,
                event.quantity,
                str(event.price) if event.price is not None else None,
                event.country,
                event.event_timestamp.isoformat(),
                ingestion_timestamp,
                topic,
                stats.run_id,
                event.query,
            )
            connection.execute(
                """INSERT INTO silver_events
                   (event_id, event_type, customer_id, product_id, order_id,
                    quantity, price, country, event_timestamp, ingestion_timestamp,
                    source_topic, pipeline_run_id, query)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            stats.records_written += 1
        if line_count < offset:
            raise ValueError(f"Committed source {topic} was truncated: {line_count} < {offset}")
        return line_count, digest.hexdigest()

    def _write_audit(self, stats: RunStats) -> None:
        with connect(self.database) as connection:
            self._store_audit(connection, stats)
        with connect(self.database) as connection:
            rows = connection.execute("SELECT * FROM pipeline_run_log ORDER BY start_time")
            write_jsonl(
                self.settings.data_dir / "gold" / "pipeline_run_log.jsonl",
                (dict(row) for row in rows),
            )

    def record_downstream_failure(self) -> None:
        """Mark the attended run failed if Gold cannot be built after Silver commits."""
        if self.last_stats is not None:
            self.last_stats.status = "FAILED"
            self._write_audit(self.last_stats)

    @staticmethod
    def _store_audit(connection: sqlite3.Connection, stats: RunStats) -> None:
        columns = ", ".join(asdict(stats))
        assignments = ", ".join(f"{key}=excluded.{key}" for key in asdict(stats) if key != "run_id")
        connection.execute(
            f"INSERT INTO pipeline_run_log ({columns}) VALUES ({','.join('?' * 11)}) "
            f"ON CONFLICT(run_id) DO UPDATE SET {assignments}",
            tuple(asdict(stats).values()),
        )

    def build_gold(self) -> dict[str, int | float]:
        """Rebuild compact local marts from validated purchase events."""
        with connect(self.database) as connection:
            orders: dict[str, list] = {}
            for event in connection.execute(
                "SELECT * FROM silver_events WHERE event_type='purchase'"
            ):
                price = Decimal(event["price"])
                if price >= Decimal("10000000000"):
                    raise ValueError(
                        "Gold unit price exceeds DECIMAL(12, 2); Silver retains raw price"
                    )
                price = price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if price >= Decimal("10000000000"):
                    raise ValueError("Rounded Gold unit price exceeds DECIMAL(12, 2)")
                row = orders.setdefault(
                    event["order_id"],
                    [
                        event["customer_id"],
                        event["event_timestamp"],
                        event["country"],
                        0,
                        Decimal(0),
                    ],
                )
                row[0] = max(filter(None, (row[0], event["customer_id"])), default=None)
                row[1] = min(row[1], event["event_timestamp"])
                row[2] = max(filter(None, (row[2], event["country"])), default=None)
                row[3] += event["quantity"]
                row[4] += event["quantity"] * price
            connection.execute("DELETE FROM fact_orders")
            connection.executemany(
                "INSERT INTO fact_orders VALUES (?, ?, ?, ?, ?, ?)",
                ((order_id, *row[:4], float(row[4])) for order_id, row in orders.items()),
            )
            connection.execute("DELETE FROM daily_sales")
            connection.execute(
                """INSERT INTO daily_sales
                   SELECT substr(order_timestamp, 1, 10), COUNT(*), SUM(units),
                          ROUND(SUM(order_total), 2), ROUND(AVG(order_total), 2)
                   FROM fact_orders GROUP BY substr(order_timestamp, 1, 10)"""
            )
            row = connection.execute(
                """SELECT COUNT(*) orders, COALESCE(SUM(units), 0) units,
                          ROUND(COALESCE(SUM(order_total), 0), 2) revenue,
                          ROUND(COALESCE(AVG(order_total), 0), 2) average_order_value
                   FROM fact_orders"""
            ).fetchone()
            metrics = dict(row)
        write_text(self.settings.data_dir / "gold" / "summary.json", json.dumps(metrics, indent=2))
        return metrics
