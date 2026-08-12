from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from retailpulse.config import Settings
from retailpulse.pipeline import RunStats
from retailpulse.storage import append_jsonl


@dataclass(frozen=True)
class Alert:
    severity: str
    metric: str
    value: float
    threshold: float
    message: str
    timestamp: str


def evaluate(stats: RunStats) -> list[Alert]:
    checks = [
        ("duplicate_rate", stats.duplicate_rate, 0.05, "Duplicate rate exceeded 5%"),
        ("rejection_rate", stats.rejection_rate, 0.02, "Rejected record rate exceeded 2%"),
        (
            "late_event_rate",
            stats.records_late / stats.records_read if stats.records_read else 0.0,
            0.05,
            "Late-event rate exceeded 5%",
        ),
    ]
    now = datetime.now(UTC).isoformat()
    return [
        Alert("warning", name, value, threshold, message, now)
        for name, value, threshold, message in checks
        if value > threshold
    ]


def publish(settings: Settings, stats: RunStats, alerts: list[Alert]) -> None:
    metric_lines = [
        "# HELP retailpulse_records_total Records seen in the latest run.",
        "# TYPE retailpulse_records_total gauge",
        f'retailpulse_records_total{{status="read"}} {stats.records_read}',
        f'retailpulse_records_total{{status="written"}} {stats.records_written}',
        f'retailpulse_records_total{{status="rejected"}} {stats.records_rejected}',
        f'retailpulse_records_total{{status="duplicate"}} {stats.records_duplicate}',
        f'retailpulse_records_total{{status="late"}} {stats.records_late}',
        "# TYPE retailpulse_duplicate_rate gauge",
        f"retailpulse_duplicate_rate {stats.duplicate_rate}",
        "# TYPE retailpulse_rejection_rate gauge",
        f"retailpulse_rejection_rate {stats.rejection_rate}",
        "# TYPE retailpulse_pipeline_duration_seconds gauge",
        f"retailpulse_pipeline_duration_seconds {stats.duration_seconds}",
        "# TYPE retailpulse_alerts gauge",
        f"retailpulse_alerts {len(alerts)}",
    ]
    (settings.data_dir / "metrics" / "retailpulse.prom").write_text(
        "\n".join(metric_lines) + "\n", encoding="utf-8"
    )
    snapshot = {"run": asdict(stats), "alerts": [asdict(alert) for alert in alerts]}
    (settings.data_dir / "metrics" / "latest.json").write_text(
        json.dumps(snapshot, indent=2), encoding="utf-8"
    )
    for alert in alerts:
        append_jsonl(settings.data_dir / "metrics" / "alerts.jsonl", asdict(alert))
