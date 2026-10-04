"""Behavioral checks for local dbt builds and the Databricks model SQL.

The cloud checks render the real model/macro files with Databricks credentials,
then run their portable SELECT statements over controlled DuckDB Silver tables.
They exercise the incremental selection contract without contacting Azure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("dbt.cli.main")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARTS = ("fact_order_items", "fact_orders", "daily_sales")
BOUNDARY = "2026-01-02T12:00:00"
LATER = "2026-01-03T12:00:00"


def purchase(event_id: str, order_id: str, quantity: int, price: int, ingested: str) -> dict:
    return {
        "event_id": event_id,
        "event_type": "purchase",
        "customer_id": "C1",
        "product_id": "P1",
        "order_id": order_id,
        "country": "IN",
        "quantity": quantity,
        "price": price,
        "event_timestamp": "2026-01-01T10:00:00",
        "ingestion_timestamp": ingested,
    }


@pytest.fixture
def local_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "dbt"
    shutil.copytree(
        PROJECT_ROOT / "dbt",
        project,
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages", ".user.yml"),
    )
    data = tmp_path / "data"
    (data / "silver").mkdir(parents=True)
    return project, data, tmp_path / "analytics.duckdb"


def write_events(data: Path, events: list[dict]) -> None:
    (data / "silver" / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )


def dbt_build(project: Path, data: Path, database: Path, *, full_refresh: bool = False) -> None:
    env = {
        **os.environ,
        "RETAILPULSE_DBT_TARGET": "local",
        "RETAILPULSE_DBT_PATH": str(database),
        "RETAILPULSE_DBT_DATA_DIR": str(data),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from dbt.cli.main import cli; cli()",
            "build",
            "--project-dir",
            str(project),
            "--profiles-dir",
            str(project),
            "--no-use-colors",
            *(["--full-refresh"] if full_refresh else []),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def rows(database: Path, query: str) -> list[tuple]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(query).fetchall()


def test_local_tied_and_later_arrivals_recompute_complete_order_and_day(local_project) -> None:
    project, data, database = local_project
    events = [purchase("E1", "O1", 2, 10, BOUNDARY)]
    write_events(data, events)
    dbt_build(project, data, database)
    assert rows(database, "select order_id, units, order_total from fact_orders") == [
        ("O1", 2, Decimal("20.00"))
    ]

    # New line on an existing order and a new order both tie the stored watermark.
    events += [purchase("E2", "O1", 1, 5, BOUNDARY), purchase("E3", "O2", 3, 7, BOUNDARY)]
    write_events(data, events)
    dbt_build(project, data, database)
    assert rows(database, "select order_item_id from fact_order_items order by 1") == [
        ("E1",),
        ("E2",),
        ("E3",),
    ]
    assert rows(database, "select order_id, units, order_total from fact_orders order by 1") == [
        ("O1", 3, Decimal("25.00")),
        ("O2", 3, Decimal("21.00")),
    ]
    assert rows(database, "select order_date, orders, units, revenue from daily_sales") == [
        (date(2026, 1, 1), 2, 6, Decimal("46.00"))
    ]

    events.append(purchase("E4", "O1", 2, 4, LATER))
    write_events(data, events)
    dbt_build(project, data, database)
    assert rows(database, "select order_id, units, order_total from fact_orders order by 1") == [
        ("O1", 5, Decimal("33.00")),
        ("O2", 3, Decimal("21.00")),
    ]
    assert rows(database, "select order_date, orders, units, revenue from daily_sales") == [
        (date(2026, 1, 1), 2, 8, Decimal("54.00"))
    ]
    assert rows(
        database,
        "select count(*), count(*) filter (where dbt_valid_to is null) "
        "from snapshots.product_snapshot",
    ) == [(3, 1)]
    assert rows(
        database,
        "select average_price from snapshots.product_snapshot where dbt_valid_to is null",
    ) == [(6.5,)]

    before = {model: rows(database, f"select * from {model} order by 1") for model in MARTS}
    snapshot_query = "select * from snapshots.product_snapshot order by product_id, dbt_valid_from"
    snapshot_before = rows(database, snapshot_query)
    # The incremental SELECT must emit no rows for the adapter to merge on a rerun.
    for model in MARTS:
        query = (
            project / "target" / "compiled" / "retailpulse" / "models" / "marts" / f"{model}.sql"
        ).read_text()
        assert rows(database, query) == []
    dbt_build(project, data, database)
    assert {model: rows(database, f"select * from {model} order by 1") for model in MARTS} == before
    assert rows(database, snapshot_query) == snapshot_before


@pytest.mark.parametrize(
    "events",
    [
        [],
        [
            {
                "event_id": "V1",
                "event_type": "search",
                "event_timestamp": "2026-01-01T10:00:00",
                "ingestion_timestamp": BOUNDARY,
            }
        ],
    ],
)
def test_local_build_accepts_empty_and_sparse_event_files(local_project, events) -> None:
    project, data, database = local_project
    write_events(data, events)
    dbt_build(project, data, database)
    assert rows(database, "select count(*) from stg_events") == [(len(events),)]
    assert rows(database, "select count(*) from fact_orders") == [(0,)]
    assert rows(database, "select count(*) from daily_sales") == [(0,)]
    if events:
        assert rows(
            database, "select customer_id, product_id, quantity, price from stg_events"
        ) == [(None, None, None, None)]


@pytest.mark.parametrize("other_order_on_old_date", [False, True])
def test_order_date_correction_matches_full_refresh(local_project, other_order_on_old_date) -> None:
    project, data, database = local_project
    events = [purchase("E1", "O1", 2, 10, BOUNDARY)]
    if other_order_on_old_date:
        events.append(purchase("E2", "O2", 1, 7, BOUNDARY))
    recent = purchase("E3", "O3", 1, 3, LATER)
    recent["event_timestamp"] = "2026-01-02T10:00:00"
    events.append(recent)
    write_events(data, events)
    dbt_build(project, data, database)
    events[0].update(
        event_timestamp="2026-01-03T10:00:00", ingestion_timestamp="2026-01-04T12:00:00"
    )
    write_events(data, events)
    dbt_build(project, data, database)

    expected = [
        (date(2026, 1, 2), 1, 1, Decimal("3.00")),
        (date(2026, 1, 3), 1, 2, Decimal("20.00")),
    ]
    if other_order_on_old_date:
        expected.insert(0, (date(2026, 1, 1), 1, 1, Decimal("7.00")))
    query = "select order_date, orders, units, revenue from daily_sales order by 1"
    assert rows(database, query) == expected
    before = rows(database, "select * from daily_sales order by 1")
    dbt_build(project, data, database, full_refresh=True)
    assert rows(database, "select * from daily_sales order by 1") == before


def cloud_sql(model: str, incremental: bool, monkeypatch) -> tuple[str, dict]:
    connections = pytest.importorskip("dbt.adapters.databricks.connections")
    from jinja2 import Environment, StrictUndefined

    credentials = connections.DatabricksCredentials(
        host="offline.invalid",
        http_path="/sql/offline",
        token="offline",
        database="fixture",
        schema="main",
    )
    target = {**credentials.to_dict(), "type": credentials.type}
    config_values = {}

    def configure(**values):
        config_values.update(values)
        return ""

    monkeypatch.setenv("RETAILPULSE_DBT_GOLD_LOCATION", "abfss://fixture/gold")
    environment = Environment(undefined=StrictUndefined)
    environment.globals.update(
        target=target,
        config=configure,
        env_var=lambda name, default: os.environ.get(name, default),
        is_incremental=lambda: incremental,
        source=lambda schema, name: f"{schema}.{name}",
        ref=lambda name: name,
        this=model,
    )
    macro = environment.from_string((PROJECT_ROOT / "dbt/macros/configure_gold.sql").read_text())
    environment.globals["configure_gold"] = macro.module.configure_gold
    prune = environment.from_string(
        (PROJECT_ROOT / "dbt/macros/prune_empty_sales_dates.sql").read_text()
    )
    environment.globals["prune_empty_sales_dates"] = prune.module.prune_empty_sales_dates
    sql = environment.from_string(
        (PROJECT_ROOT / f"dbt/models/marts/{model}.sql").read_text()
    ).render()
    if config_values.get("pre_hook"):
        config_values["pre_hook"] = environment.from_string(config_values["pre_hook"]).render()
    return sql, config_values


def cloud_build(connection, monkeypatch, incremental: bool) -> dict[str, list[tuple]]:
    candidates = {}
    for model in MARTS:
        sql, config = cloud_sql(model, incremental, monkeypatch)
        assert config["file_format"] == "delta"
        assert config["incremental_strategy"] == "merge"
        assert config["location_root"] == "abfss://fixture/gold"
        if incremental:
            if config.get("pre_hook", "").strip():
                connection.execute(config["pre_hook"])
            connection.execute(f"create or replace temp table incoming as {sql}")
            candidates[model] = connection.execute("select * from incoming order by 1").fetchall()
            key = {
                "fact_order_items": "order_item_id",
                "fact_orders": "order_id",
                "daily_sales": "order_date",
            }[model]
            connection.execute(f"delete from {model} where {key} in (select {key} from incoming)")
            connection.execute(f"insert into {model} select * from incoming")
        else:
            connection.execute(f"create table {model} as {sql}")
    return candidates


@pytest.mark.parametrize("item_ingested", [BOUNDARY, LATER])
def test_cloud_item_only_arrivals_recompute_headers_and_daily_sales(
    monkeypatch, item_ingested
) -> None:
    with duckdb.connect() as connection:
        connection.execute("create schema silver")
        connection.execute("""
            create table silver.orders (
                order_id varchar, customer_id varchar, order_timestamp timestamp,
                country varchar, ingestion_timestamp timestamp
            )
        """)
        connection.execute("""
            create table silver.order_items (
                _record_hash varchar, order_id varchar, product_id varchar, quantity integer,
                unit_price decimal(12, 2), ingestion_timestamp timestamp
            )
        """)
        connection.execute(
            "insert into silver.orders values (?, ?, ?, ?, ?)",
            ["O1", "C1", "2026-01-01 10:00:00", "IN", BOUNDARY],
        )
        connection.execute(
            "insert into silver.order_items values (?, ?, ?, ?, ?, ?)",
            ["I1", "O1", "P1", 2, 10, BOUNDARY],
        )
        cloud_build(connection, monkeypatch, incremental=False)

        connection.execute(
            "insert into silver.order_items values (?, ?, ?, ?, ?, ?)",
            ["I2", "O1", "P2", 1, 5, item_ingested],
        )
        cloud_build(connection, monkeypatch, incremental=True)
        assert connection.execute("select units, order_total from fact_orders").fetchall() == [
            (3, Decimal("25.00"))
        ]
        assert connection.execute(
            "select order_item_id from fact_order_items order by 1"
        ).fetchall() == [("I1",), ("I2",)]
        assert connection.execute("select orders, units, revenue from daily_sales").fetchall() == [
            (1, 3, Decimal("25.00"))
        ]

        connection.execute(
            "insert into silver.order_items values (?, ?, ?, ?, ?, ?)",
            ["I3", "O1", "P3", 2, 4, "2026-01-04T12:00:00"],
        )
        cloud_build(connection, monkeypatch, incremental=True)
        assert connection.execute("select units, order_total from fact_orders").fetchall() == [
            (5, Decimal("33.00"))
        ]
        assert connection.execute("select orders, units, revenue from daily_sales").fetchall() == [
            (1, 5, Decimal("33.00"))
        ]
        assert connection.execute("select ingestion_timestamp from silver.orders").fetchall() == [
            (datetime(2026, 1, 2, 12),)
        ]

        # A source correction at the same ingestion time must replace the line and rollups.
        connection.execute("update silver.order_items set quantity = 3 where _record_hash = 'I3'")
        cloud_build(connection, monkeypatch, incremental=True)
        assert connection.execute(
            "select quantity from fact_order_items where order_item_id = 'I3'"
        ).fetchall() == [(3,)]
        assert connection.execute("select units, order_total from fact_orders").fetchall() == [
            (6, Decimal("37.00"))
        ]
        assert connection.execute("select orders, units, revenue from daily_sales").fetchall() == [
            (1, 6, Decimal("37.00"))
        ]
        before = {
            model: connection.execute(f"select * from {model} order by 1").fetchall()
            for model in MARTS
        }
        assert cloud_build(connection, monkeypatch, incremental=True) == {
            "fact_order_items": [],
            "fact_orders": [],
            "daily_sales": [],
        }
        assert {
            model: connection.execute(f"select * from {model} order by 1").fetchall()
            for model in MARTS
        } == before

        connection.execute(
            "update silver.orders set order_timestamp = '2026-01-03 10:00:00', "
            "ingestion_timestamp = '2026-01-05 12:00:00' where order_id = 'O1'"
        )
        cloud_build(connection, monkeypatch, incremental=True)
        assert connection.execute(
            "select order_date, orders, units, revenue from daily_sales order by 1"
        ).fetchall() == [(date(2026, 1, 3), 1, 6, Decimal("37.00"))]
