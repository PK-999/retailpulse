#!/usr/bin/env python3
"""Prove the local portfolio flow in isolated data; never reuse or reset an existing folder."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from retailpulse.config import Settings
from retailpulse.incident import generate_report
from retailpulse.monitoring import evaluate, publish
from retailpulse.pipeline import LocalMedallionPipeline
from retailpulse.producer import produce
from retailpulse.storage import connect, write_text

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    ("normal", 100, 42),
    ("duplicate", 60, 7),
    ("malformed", 20, 7),
    ("late-data", 15, 7),
    ("traffic-spike", 10, 42),
)
MARTS = ("fact_order_items", "fact_orders", "daily_sales")


def run_dbt(data_dir: Path, executable: str, full_refresh: bool = False) -> dict:
    command = [
        executable,
        "build",
        "--project-dir",
        str(ROOT / "dbt"),
        "--profiles-dir",
        str(ROOT / "dbt"),
        "--target",
        "local",
    ]
    if full_refresh:
        command.append("--full-refresh")
    environment = {
        **os.environ,
        "RETAILPULSE_DBT_DATA_DIR": str(data_dir),
        "RETAILPULSE_DBT_PATH": str(data_dir / "gold" / "warehouse.duckdb"),
        "DBT_TARGET_PATH": str(data_dir / "dbt-target"),
        "DBT_LOG_PATH": str(data_dir / "dbt-logs"),
    }
    result = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=180, check=False
    )
    if result.returncode:
        raise RuntimeError(f"dbt failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    results = json.loads((data_dir / "dbt-target" / "run_results.json").read_text())
    statuses = [row["status"] for row in results["results"]]
    if any(status not in {"success", "pass"} for status in statuses):
        raise RuntimeError(f"dbt did not pass every node: {statuses}")
    return {"nodes_passed": len(statuses), "elapsed_seconds": results["elapsed_time"]}


def mart_rows(database: Path) -> dict:
    with duckdb.connect(str(database), read_only=True) as connection:
        return {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY ALL").fetchall()
            for name in MARTS
        }


def verify_flow(data_dir: Path, dbt_bin: str, use_ollama: bool = False) -> dict:
    started = time.monotonic()
    settings = Settings(
        data_dir,
        "unused",
        False,
        os.getenv("OLLAMA_URL", "http://localhost:11434"),
        os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        60,
    )
    pipeline = LocalMedallionPipeline(settings)
    batches = []
    incident = None
    for scenario, count, seed in SCENARIOS:
        produced = produce(settings, count, scenario, seed)
        stats = pipeline.process()
        if produced != stats.records_read:
            raise RuntimeError(f"Incomplete input consumption for {scenario}")
        if stats.records_read != (
            stats.records_written
            + stats.records_rejected
            + stats.records_late
            + stats.records_duplicate
        ):
            raise RuntimeError(f"Classification did not reconcile for {scenario}")
        alerts = evaluate(stats)
        publish(settings, stats, alerts)
        pipeline.build_gold()
        batches.append(
            {
                "scenario": scenario,
                **asdict(stats),
                "alert_metrics": [alert.metric for alert in alerts],
            }
        )
        print(
            f"{scenario}: read={stats.records_read}, Silver={stats.records_written}, "
            f"rejected={stats.records_rejected}, late={stats.records_late}, "
            f"duplicates={stats.records_duplicate}",
            flush=True,
        )
        if scenario == "duplicate":
            report, source = generate_report(settings, stats, alerts, use_ollama=use_ollama)
            incident = {"source": source, "report": report}
    if pipeline.process().records_read != 0:
        raise RuntimeError("No-op ingestion rerun unexpectedly read input")
    clean = run_dbt(data_dir, dbt_bin)
    database = data_dir / "gold" / "warehouse.duckdb"
    original = mart_rows(database)
    rerun = run_dbt(data_dir, dbt_bin)
    if mart_rows(database) != original:
        raise RuntimeError("No-op incremental dbt rerun changed marts")
    refresh = run_dbt(data_dir, dbt_bin, full_refresh=True)
    if mart_rows(database) != original:
        raise RuntimeError("Incremental and full-refresh marts disagree")
    with duckdb.connect(str(database), read_only=True) as connection:
        source = connection.execute("""SELECT COUNT(*), COUNT(DISTINCT order_id),
                   COALESCE(SUM(quantity), 0), COALESCE(SUM(quantity * price), 0)
                   FROM stg_events WHERE event_type = 'purchase'""").fetchone()
        items = connection.execute("""SELECT COUNT(*), COUNT(DISTINCT order_id),
                   COALESCE(SUM(quantity), 0), COALESCE(SUM(line_total), 0)
                   FROM fact_order_items""").fetchone()
        orders = connection.execute("""SELECT COUNT(*), COALESCE(SUM(units), 0),
                   COALESCE(SUM(order_total), 0) FROM fact_orders""").fetchone()
        daily = connection.execute("""SELECT COALESCE(SUM(orders), 0),
                   COALESCE(SUM(units), 0), COALESCE(SUM(revenue), 0)
                   FROM daily_sales""").fetchone()
        if source != items or items[1:] != orders or orders != daily:
            raise RuntimeError(f"Gold reconciliation failed: {source}, {items}, {orders}, {daily}")
    with connect(pipeline.database) as connection:
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("bronze_events", "silver_events", "quarantine")
        }
    return {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "scope": "isolated local files / SQLite / DuckDB; cloud and broker checked separately",
        "python_version": sys.version.split()[0],
        "batches": batches,
        "counts": counts,
        "gold": {
            "items": items[0],
            "orders": orders[0],
            "units": int(orders[1]),
            "revenue": str(orders[2]),
        },
        "dbt": {
            "clean": clean,
            "incremental": rerun,
            "full_refresh": refresh,
            "unchanged_rerun": True,
            "full_refresh_equivalent": True,
        },
        "incident": incident,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, help="Keep evidence in a NEW data directory")
    parser.add_argument("--output", type=Path, help="Save the safe aggregate evidence report")
    parser.add_argument(
        "--dbt-bin",
        default=os.getenv("RETAILPULSE_DBT_BIN", str(Path(sys.executable).parent / "dbt")),
    )
    parser.add_argument(
        "--ollama", action="store_true", help="Try local Ollama, with rule fallback"
    )
    args = parser.parse_args()
    if args.work_dir:
        args.work_dir = args.work_dir.resolve()
        args.work_dir.mkdir(parents=True, exist_ok=False)
        report = verify_flow(args.work_dir, args.dbt_bin, args.ollama)
    else:
        with tempfile.TemporaryDirectory(prefix="retailpulse-e2e-") as temporary:
            report = verify_flow(Path(temporary), args.dbt_bin, args.ollama)
    if args.output:
        write_text(args.output, json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
