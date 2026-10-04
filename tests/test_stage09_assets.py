from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "bi-dashboard" / "public" / "data" / "dashboard.json"
SPEC = spec_from_file_location("stage09_exporter", ROOT / "scripts" / "export_stage09_dashboard.py")
assert SPEC and SPEC.loader
EXPORTER = module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)
relation = EXPORTER.relation
validate_reconciliation = EXPORTER.validate_reconciliation


def test_stage09_snapshot_is_verified_and_public_safe() -> None:
    raw = SNAPSHOT.read_text(encoding="utf-8")
    snapshot = json.loads(raw)

    assert snapshot["schemaVersion"] == "1.0"
    assert snapshot["metadata"]["source"] == "Azure Databricks Gold"
    assert snapshot["metadata"]["status"] == "verified"
    assert snapshot["metadata"]["queryVersion"] == "stage09-v1"
    assert snapshot["reconciliation"]["checksPassed"] == 5
    assert snapshot["reconciliation"]["checksTotal"] == 5
    assert snapshot["kpis"]["revenue"] == snapshot["reconciliation"]["goldRevenue"]
    assert snapshot["dailySales"]
    assert snapshot["countrySales"]
    assert snapshot["topProducts"]
    assert snapshot["topCustomers"]
    assert snapshot["eventRate"]

    lowered = raw.lower()
    for forbidden in ("databricks_token", "access_token", "bearer ", "connection_string"):
        assert forbidden not in lowered


def test_stage09_reconciliation_fails_closed() -> None:
    metrics = {
        "silver_customers": 10,
        "gold_customers": 9,
        "silver_products": 4,
        "gold_products": 4,
        "silver_order_items": 20,
        "gold_order_items": 20,
        "silver_revenue": 100.0,
        "gold_revenue": 100.0,
        "daily_revenue": 100.0,
    }

    with pytest.raises(RuntimeError, match="customers"):
        validate_reconciliation(metrics)


def test_stage09_databricks_identifiers_are_quoted_and_validated() -> None:
    assert relation("catalog_1", "retailpulse_gold", "fact_orders") == (
        "`catalog_1`.`retailpulse_gold`.`fact_orders`"
    )
    with pytest.raises(ValueError, match="Unsupported"):
        relation("catalog; DROP", "retailpulse_gold", "fact_orders")


def valid_reconciliation() -> dict:
    return {
        "silver_customers": 2,
        "gold_customers": 2,
        "silver_products": 3,
        "gold_products": 3,
        "silver_order_items": 4,
        "gold_order_items": 4,
        "silver_revenue": Decimal("120.50"),
        "gold_revenue": Decimal("120.50"),
        "daily_revenue": Decimal("120.50"),
    }


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1, True, "2", 2.5])
def test_reconciliation_rejects_invalid_counts_even_if_both_sides_match(value) -> None:
    metrics = valid_reconciliation()
    metrics["silver_customers"] = metrics["gold_customers"] = value
    with pytest.raises(ValueError, match="count|numeric|finite|missing"):
        validate_reconciliation(metrics)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1, True, "120.50"])
def test_reconciliation_rejects_invalid_amounts_even_if_all_sides_match(value) -> None:
    metrics = valid_reconciliation()
    for key in ("silver_revenue", "gold_revenue", "daily_revenue"):
        metrics[key] = value
    with pytest.raises(ValueError, match="amount|numeric|finite|missing"):
        validate_reconciliation(metrics)


def test_reconciliation_rejects_missing_fields() -> None:
    metrics = valid_reconciliation()
    del metrics["gold_products"]
    with pytest.raises(ValueError, match="gold_products"):
        validate_reconciliation(metrics)


class SnapshotCursor:
    """The external SQL boundary returns full aggregate result sets."""

    def __init__(self, *, empty=False):
        now = datetime(2026, 8, 12, 12, tzinfo=UTC)
        self.rows = [
            [
                {
                    "orders": 2,
                    "units": 4,
                    "revenue": Decimal("120.50"),
                    "average_order_value": Decimal("60.25"),
                    "window_start": "2011-01-01",
                    "window_end": "2011-01-01",
                    "gold_updated_at": now,
                }
            ],
            [{"product_views": 2, "purchases": 3, "stream_updated_at": now}],
            [
                {
                    "date": "2011-01-01",
                    "orders": 2,
                    "units": 4,
                    "revenue": Decimal("120.50"),
                    "average_order_value": Decimal("60.25"),
                }
            ],
            [{"country": "United Kingdom", "orders": 2, "revenue": Decimal("120.50")}],
            [{"product_id": "P1", "units": 4, "revenue": Decimal("120.50")}],
            [
                {
                    "customer_id": "C1",
                    "country": "United Kingdom",
                    "orders": 2,
                    "lifetime_value": Decimal("120.50"),
                }
            ],
            [{"healthy": 1, "stale": 0, "unknown": 2}],
            [
                {
                    "product_id": "P1",
                    "units_updated": 4,
                    "last_update": now,
                    "freshness_minutes": 5,
                    "status": "healthy",
                }
            ],
            [{"minute": "2026-08-12 12:00:00", "events": 5}],
            [{"historical_completed_at": now, "streaming_completed_at": now}],
            [valid_reconciliation()],
        ]
        if empty:
            self.rows[0] = [
                {
                    "orders": 0,
                    "units": 0,
                    "revenue": 0,
                    "average_order_value": 0,
                    "window_start": None,
                    "window_end": None,
                    "gold_updated_at": None,
                }
            ]
            self.rows[1] = [{"product_views": 0, "purchases": 0, "stream_updated_at": None}]
            self.rows[6] = [{"healthy": 0, "stale": 0, "unknown": 0}]
            self.rows[9] = [{"historical_completed_at": None, "streaming_completed_at": None}]
            self.rows[10] = [{key: 0 for key in valid_reconciliation()}]
            for index in (2, 3, 4, 5, 7, 8):
                self.rows[index] = []
        self.index = -1

    def execute(self, query):
        self.index += 1
        self.description = (
            [(key,) for key in self.rows[self.index][0]] if self.rows[self.index] else []
        )

    def fetchall(self):
        return [tuple(row.values()) for row in self.rows[self.index]]


def build(cursor):
    return EXPORTER.build_snapshot(
        cursor, catalog="demo", gold_schema="gold", silver_schema="silver", ops_schema="ops"
    )


def test_exported_snapshot_reconciles_real_query_results() -> None:
    snapshot = build(SnapshotCursor())
    assert snapshot["kpis"]["revenue"] == 120.50
    assert snapshot["kpis"]["conversionRate"] == 1.5  # Independent events can exceed 100%.
    assert snapshot["reconciliation"]["checksPassed"] == 5
    assert snapshot["metadata"]["goldUpdatedAt"] == "2026-08-12T12:00:00+00:00"


@pytest.mark.parametrize(
    "index,field,value",
    [
        (0, "revenue", 999),
        (0, "orders", 3),
        (0, "units", 7),
        (2, "revenue", 119),
        (2, "units", 5),
    ],
)
def test_exporter_rejects_internally_inconsistent_dashboard(index, field, value) -> None:
    cursor = SnapshotCursor()
    cursor.rows[index][0][field] = value
    with pytest.raises(RuntimeError, match="dashboard|KPI|daily"):
        build(cursor)


def test_exporter_empty_query_is_a_clear_failure() -> None:
    cursor = SnapshotCursor()
    cursor.rows[0] = []
    with pytest.raises(ValueError, match="KPI|aggregate"):
        build(cursor)


def test_empty_sales_snapshot_has_no_fabricated_ratio_or_window() -> None:
    snapshot = build(SnapshotCursor(empty=True))
    assert snapshot["kpis"]["conversionRate"] is None
    assert snapshot["metadata"]["businessWindow"] == {
        "start": None,
        "end": None,
        "label": "No sales observations",
    }
    assert snapshot["metadata"]["lastSuccessfulRunAt"] is None
    assert snapshot["dailySales"] == []
    assert snapshot["reconciliation"]["checksPassed"] == 5


def test_nonfinite_json_retains_previous_snapshot_and_removes_temporary_file(tmp_path) -> None:
    output = tmp_path / "dashboard.json"
    output.write_text('{"previous":true}\n')
    with pytest.raises(ValueError):
        EXPORTER.write_snapshot({"revenue": float("nan")}, output)
    assert output.read_text() == '{"previous":true}\n'
    assert list(tmp_path.iterdir()) == [output]


def test_snapshot_write_is_deterministic_for_identical_input(tmp_path) -> None:
    snapshot = build(SnapshotCursor())
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    EXPORTER.write_snapshot(snapshot, first)
    EXPORTER.write_snapshot(snapshot, second)
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text())["kpis"]["revenue"] == 120.50


def run_attended_runner(tmp_path, *, state="STOPPED", export_exit=0, stop_mode="success"):
    commands = tmp_path / "bin"
    commands.mkdir()
    log = tmp_path / "actions.log"
    scripts = {
        "curl": """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
url = args[args.index("--url") + 1]
method = args[args.index("--request") + 1]
with open(os.environ["ACTION_LOG"], "a") as f: f.write(method + " " + url + "\\n")
state = os.environ["INITIAL_STATE"]
counter = Path(os.environ["ACTION_LOG"] + ".polls")
polls = int(counter.read_text()) if counter.exists() else 0
stopped = Path(os.environ["ACTION_LOG"] + ".stopped")
if url.endswith("/stop"):
    if os.environ["STOP_MODE"] == "rejected":
        print("Stop request rejected", file=sys.stderr)
        sys.exit(22)
    stopped.write_text("requested")
if method == "GET":
    counter.write_text(str(polls + 1))
    if stopped.exists():
        state = "STOPPING" if os.environ["STOP_MODE"] == "timeout" else "STOPPED"
    elif state == "STOPPED": state = "STOPPED" if polls == 0 else "RUNNING"
    print(json.dumps({"state": state}))
else: print("{}")
""",
        "date": """#!/usr/bin/env python3
import os
from pathlib import Path
counter = Path(os.environ["ACTION_LOG"] + ".clock")
ticks = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(ticks + 1))
print(1000 + ticks * 15)
""",
        "sleep": "#!/usr/bin/env bash\nexit 0\n",
        "npm": '#!/usr/bin/env bash\nprintf "npm %s\\n" "$*" >> "$ACTION_LOG"\n',
        "python": (
            """#!/usr/bin/env bash
printf "exporter\n" >> "$ACTION_LOG"
exit "$EXPORT_EXIT"
"""
        ),
    }
    for name, source in scripts.items():
        path = commands / name
        path.write_text(source)
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{commands}:{os.environ['PATH']}",
        "DATABRICKS_TOKEN": "test-only-token",
        "ACTION_LOG": str(log),
        "INITIAL_STATE": state,
        "EXPORT_EXIT": str(export_exit),
        "STOP_MODE": stop_mode,
        "RETAILPULSE_WAREHOUSE_STOP_TIMEOUT_SECONDS": "30",
        "RETAILPULSE_PYTHON_BIN": str(commands / "python"),
        "RETAILPULSE_WAREHOUSE_START_TIMEOUT_SECONDS": "30",
    }
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run_stage09_bi_dashboard.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result, log.read_text()


@pytest.mark.parametrize("export_exit", [0, 7])
def test_attended_runner_always_stops_compute_and_preserves_export_failure(tmp_path, export_exit):
    result, actions = run_attended_runner(tmp_path, export_exit=export_exit)
    assert result.returncode == export_exit
    assert "/start" in actions
    assert any(line.endswith("/stop") for line in actions.splitlines())
    assert "test-only-token" not in result.stdout + result.stderr + actions
    assert ("npm" in actions) == (export_exit == 0)
    assert "confirmed STOPPED" in result.stdout


def test_attended_runner_bounds_stopping_state_and_stops_on_timeout(tmp_path):
    result, actions = run_attended_runner(tmp_path, state="STOPPING")
    assert result.returncode != 0
    assert "within 30s" in result.stderr
    assert any(line.endswith("/stop") for line in actions.splitlines())
    assert "exporter" not in actions


@pytest.mark.parametrize("stop_mode", ["rejected", "timeout"])
@pytest.mark.parametrize("export_exit", [0, 7])
def test_runner_cleanup_failure_is_loud_and_preserves_original_failure(
    tmp_path, stop_mode, export_exit
):
    result, actions = run_attended_runner(tmp_path, export_exit=export_exit, stop_mode=stop_mode)
    assert result.returncode == (export_exit or 1)
    assert "WARNING" in result.stderr
    assert "could not confirm STOPPED" in result.stderr
    assert "confirmed STOPPED" not in result.stdout
    assert 1 <= sum(line.endswith("/stop") for line in actions.splitlines()) <= 3
    assert "test-only-token" not in result.stdout + result.stderr + actions
