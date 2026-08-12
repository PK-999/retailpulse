from __future__ import annotations

import json
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from retailpulse.config import Settings
from retailpulse.contracts import QuarantineRecord, RetailEvent
from retailpulse.storage import append_jsonl, connect, initialize_database, utc_now


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

    Inbox offsets are line counts persisted per topic. Bronze is append-only, Silver is
    idempotent by event_id, and invalid payloads are always retained in quarantine.
    """

    watermark = timedelta(minutes=30)

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_directories()
        self.database = settings.data_dir / "retailpulse.db"
        initialize_database(self.database)

    def _checkpoint(self, topic: str) -> Path:
        return self.settings.data_dir / "checkpoints" / f"{topic}.offset"

    def _offset(self, topic: str) -> int:
        path = self._checkpoint(topic)
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _save_offset(self, topic: str, offset: int) -> None:
        self._checkpoint(topic).write_text(str(offset), encoding="utf-8")

    def _quarantine(self, connection, raw: str, error_type: str, message: str) -> None:
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
        append_jsonl(
            self.settings.data_dir / "quarantine" / "events.jsonl",
            record.model_dump(mode="json"),
        )

    def process(self) -> RunStats:
        started = time.monotonic()
        now = datetime.now(UTC)
        stats = RunStats(
            run_id=str(uuid4()), pipeline_name="local_bronze_silver", start_time=now.isoformat()
        )
        topics = ("customer-events", "order-events", "inventory-events")
        try:
            with connect(self.database) as connection:
                for topic in topics:
                    source = self.settings.data_dir / "inbox" / f"{topic}.jsonl"
                    if not source.exists():
                        continue
                    lines = source.read_text(encoding="utf-8").splitlines()
                    offset = self._offset(topic)
                    for raw in lines[offset:]:
                        stats.records_read += 1
                        ingestion_timestamp = utc_now()
                        append_jsonl(
                            self.settings.data_dir / "bronze" / f"{topic}.jsonl",
                            {
                                "raw_payload": raw,
                                "source_topic": topic,
                                "ingestion_timestamp": ingestion_timestamp,
                                "pipeline_run_id": stats.run_id,
                            },
                        )
                        try:
                            event = RetailEvent.model_validate_json(raw)
                        except (ValidationError, ValueError) as error:
                            stats.records_rejected += 1
                            self._quarantine(connection, raw, "SCHEMA_VALIDATION", str(error))
                            continue
                        event_id = str(event.event_id)
                        exists = connection.execute(
                            "SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)
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
                        connection.execute(
                            "INSERT INTO processed_events (event_id, processed_at) VALUES (?, ?)",
                            (event_id, ingestion_timestamp),
                        )
                        values = (
                            event_id,
                            event.event_type,
                            event.customer_id,
                            event.product_id,
                            event.order_id,
                            event.quantity,
                            float(event.price) if event.price is not None else None,
                            event.country,
                            event.event_timestamp.isoformat(),
                            ingestion_timestamp,
                            topic,
                            stats.run_id,
                        )
                        connection.execute(
                            """INSERT INTO silver_events
                               (event_id, event_type, customer_id, product_id, order_id,
                                quantity, price, country, event_timestamp, ingestion_timestamp,
                                source_topic, pipeline_run_id)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            values,
                        )
                        append_jsonl(
                            self.settings.data_dir / "silver" / "events.jsonl",
                            event.model_dump(mode="json")
                            | {
                                "source_topic": topic,
                                "ingestion_timestamp": ingestion_timestamp,
                                "pipeline_run_id": stats.run_id,
                            },
                        )
                        stats.records_written += 1
                    self._save_offset(topic, len(lines))
                stats.status = "SUCCESS"
        except Exception:
            stats.status = "FAILED"
            raise
        finally:
            stats.end_time = utc_now()
            stats.duration_seconds = round(time.monotonic() - started, 6)
            self._write_audit(stats)
        return stats

    def _write_audit(self, stats: RunStats) -> None:
        with connect(self.database) as connection:
            connection.execute(
                """INSERT INTO pipeline_run_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    stats.run_id,
                    stats.pipeline_name,
                    stats.start_time,
                    stats.end_time,
                    stats.status,
                    stats.records_read,
                    stats.records_written,
                    stats.records_rejected,
                    stats.records_duplicate,
                    stats.records_late,
                    stats.duration_seconds,
                ),
            )
        append_jsonl(self.settings.data_dir / "gold" / "pipeline_run_log.jsonl", asdict(stats))

    def build_gold(self) -> dict[str, int | float]:
        """Incrementally rebuild compact local marts from validated purchase events."""
        with connect(self.database) as connection:
            connection.execute("DELETE FROM fact_orders")
            connection.execute(
                """INSERT INTO fact_orders
                   SELECT order_id, MAX(customer_id), MIN(event_timestamp), MAX(country),
                          SUM(COALESCE(quantity, 0)),
                          SUM(COALESCE(quantity, 0) * COALESCE(price, 0))
                   FROM silver_events
                   WHERE event_type = 'purchase' AND order_id IS NOT NULL
                   GROUP BY order_id"""
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
        (self.settings.data_dir / "gold" / "summary.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )
        return metrics
