from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def relation(catalog: str, schema: str, table: str) -> str:
    for value in (catalog, schema, table):
        if not IDENTIFIER.fullmatch(value):
            raise ValueError(f"Unsupported Databricks identifier: {value!r}")
    return f"`{catalog}`.`{schema}`.`{table}`"


def public_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        timestamp = value
        if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.isoformat()
    return value


def fetch_rows(cursor: Any, query: str) -> list[dict[str, Any]]:
    cursor.execute(query)
    columns = [description[0].lower() for description in cursor.description]
    return [
        {name: public_value(value) for name, value in zip(columns, row, strict=True)}
        for row in cursor.fetchall()
    ]


def as_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Missing or non-numeric count")
    if not math.isfinite(value) or value < 0 or value != int(value):
        raise ValueError("Count must be a finite non-negative integer")
    return int(value)


def as_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Missing or non-numeric amount")
    if not math.isfinite(value) or value < 0:
        raise ValueError("Amount must be finite and non-negative")
    return round(float(value), 2)


def aggregate(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    if len(rows) != 1:
        raise ValueError(f"{name} aggregate must return exactly one row; received {len(rows)}")
    return rows[0]


def validate_reconciliation(reconciliation: dict[str, Any]) -> None:
    required = (
        "silver_customers",
        "gold_customers",
        "silver_products",
        "gold_products",
        "silver_order_items",
        "gold_order_items",
        "silver_revenue",
        "gold_revenue",
        "daily_revenue",
    )
    missing = [key for key in required if key not in reconciliation]
    if missing:
        raise ValueError(f"Missing reconciliation fields: {', '.join(missing)}")
    checks = {
        "customers": as_int(reconciliation["silver_customers"])
        == as_int(reconciliation["gold_customers"]),
        "products": as_int(reconciliation["silver_products"])
        == as_int(reconciliation["gold_products"]),
        "order_items": as_int(reconciliation["silver_order_items"])
        == as_int(reconciliation["gold_order_items"]),
        "revenue": as_float(reconciliation["silver_revenue"])
        == as_float(reconciliation["gold_revenue"]),
        "daily_revenue": as_float(reconciliation["gold_revenue"])
        == as_float(reconciliation["daily_revenue"]),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise RuntimeError(f"Stage 9 reconciliation failed: {', '.join(failures)}")
    reconciliation["checks_passed"] = sum(checks.values())
    reconciliation["checks_total"] = len(checks)


def build_snapshot(
    cursor: Any,
    *,
    catalog: str,
    gold_schema: str,
    silver_schema: str,
    ops_schema: str,
) -> dict[str, Any]:
    def gold(table: str) -> str:
        return relation(catalog, gold_schema, table)

    def silver(table: str) -> str:
        return relation(catalog, silver_schema, table)

    def ops(table: str) -> str:
        return relation(catalog, ops_schema, table)

    kpis = aggregate(
        fetch_rows(
            cursor,
            f"""
        SELECT
          COUNT(*) AS orders,
          COALESCE(SUM(units), 0) AS units,
          ROUND(COALESCE(SUM(order_total), 0), 2) AS revenue,
          ROUND(COALESCE(AVG(order_total), 0), 2) AS average_order_value,
          MIN(CAST(order_timestamp AS DATE)) AS window_start,
          MAX(CAST(order_timestamp AS DATE)) AS window_end,
          MAX(ingestion_timestamp) AS gold_updated_at
        FROM {gold("fact_orders")}
        """,
        ),
        "KPI",
    )
    conversion = aggregate(
        fetch_rows(
            cursor,
            f"""
        SELECT
          COALESCE(SUM(CASE WHEN event_type = 'product_view' THEN 1 ELSE 0 END), 0)
            AS product_views,
          COALESCE(SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END), 0) AS purchases,
          MAX(ingestion_timestamp) AS stream_updated_at
        FROM {silver("streaming_events")}
        """,
        ),
        "Event counts",
    )
    daily_sales = fetch_rows(
        cursor,
        f"""
        SELECT
          CAST(order_date AS STRING) AS date,
          orders,
          units,
          ROUND(revenue, 2) AS revenue,
          ROUND(average_order_value, 2) AS average_order_value
        FROM {gold("daily_sales")}
        ORDER BY order_date
        """,
    )
    country_sales = fetch_rows(
        cursor,
        f"""
        SELECT country, COUNT(*) AS orders, ROUND(SUM(order_total), 2) AS revenue
        FROM {gold("fact_orders")}
        GROUP BY country
        ORDER BY revenue DESC, country
        LIMIT 12
        """,
    )
    top_products = fetch_rows(
        cursor,
        f"""
        SELECT product_id, SUM(quantity) AS units, ROUND(SUM(line_total), 2) AS revenue
        FROM {gold("fact_order_items")}
        GROUP BY product_id
        ORDER BY revenue DESC, product_id
        LIMIT 10
        """,
    )
    top_customers = fetch_rows(
        cursor,
        f"""
        SELECT customer_id, country, lifetime_orders AS orders,
               ROUND(lifetime_value, 2) AS lifetime_value
        FROM {gold("customer_360")}
        ORDER BY lifetime_value DESC, customer_id
        LIMIT 10
        """,
    )
    inventory_summary = aggregate(
        fetch_rows(
            cursor,
            f"""
        SELECT
          COALESCE(SUM(CASE WHEN inventory_status = 'healthy' THEN 1 ELSE 0 END), 0) AS healthy,
          COALESCE(SUM(CASE WHEN inventory_status = 'stale' THEN 1 ELSE 0 END), 0) AS stale,
          COALESCE(SUM(CASE WHEN inventory_status = 'unknown' THEN 1 ELSE 0 END), 0) AS unknown
        FROM {gold("inventory_health")}
        """,
        ),
        "Inventory",
    )
    inventory_products = fetch_rows(
        cursor,
        f"""
        SELECT product_id, units_updated, last_inventory_update AS last_update,
               freshness_minutes, inventory_status AS status
        FROM {gold("inventory_health")}
        ORDER BY
          CASE inventory_status WHEN 'healthy' THEN 0 WHEN 'stale' THEN 1 ELSE 2 END,
          last_inventory_update DESC NULLS LAST,
          product_id
        LIMIT 10
        """,
    )
    event_rate = fetch_rows(
        cursor,
        f"""
        SELECT CAST(DATE_TRUNC('minute', ingestion_timestamp) AS STRING) AS minute,
               COUNT(*) AS events
        FROM {silver("streaming_events")}
        GROUP BY DATE_TRUNC('minute', ingestion_timestamp)
        ORDER BY DATE_TRUNC('minute', ingestion_timestamp)
        """,
    )
    latest_runs = aggregate(
        fetch_rows(
            cursor,
            f"""
        SELECT
          (SELECT MAX(completed_at) FROM {ops("historical_batch_runs")}
            WHERE status = 'SUCCESS') AS historical_completed_at,
          (SELECT MAX(completed_at) FROM {ops("streaming_batch_runs")}) AS streaming_completed_at
        """,
        ),
        "Pipeline runs",
    )
    reconciliation = aggregate(
        fetch_rows(
            cursor,
            f"""
        SELECT
          (SELECT COUNT(*) FROM {silver("customers")}) AS silver_customers,
          (SELECT COUNT(*) FROM {gold("dim_customer")}) AS gold_customers,
          (SELECT COUNT(*) FROM {silver("products")}) AS silver_products,
          (SELECT COUNT(*) FROM {gold("dim_product")}) AS gold_products,
          (SELECT COUNT(*) FROM {silver("order_items")}) AS silver_order_items,
          (SELECT COUNT(*) FROM {gold("fact_order_items")}) AS gold_order_items,
          (SELECT ROUND(COALESCE(SUM(quantity * unit_price), 0), 2) FROM {silver("order_items")})
            AS silver_revenue,
          (SELECT ROUND(COALESCE(SUM(line_total), 0), 2) FROM {gold("fact_order_items")})
            AS gold_revenue,
          (SELECT ROUND(COALESCE(SUM(revenue), 0), 2) FROM {gold("daily_sales")}) AS daily_revenue
        """,
        ),
        "Reconciliation",
    )
    validate_reconciliation(reconciliation)

    for field in ("revenue", "orders", "units"):
        convert = as_float if field == "revenue" else as_int
        total = convert(sum(convert(row[field]) for row in daily_sales))
        if convert(kpis[field]) != total:
            raise RuntimeError(f"Stage 9 dashboard KPI {field} does not match daily sales")
    if as_float(kpis["revenue"]) != as_float(reconciliation["gold_revenue"]):
        raise RuntimeError("Stage 9 dashboard KPI revenue does not match reconciled Gold")

    views = as_int(conversion["product_views"])
    purchases = as_int(conversion["purchases"])
    completed_candidates = [
        value
        for value in (
            latest_runs["historical_completed_at"],
            latest_runs["streaming_completed_at"],
        )
        if value
    ]
    last_successful_run = (
        max(completed_candidates) if completed_candidates else kpis["gold_updated_at"]
    )

    return {
        "schemaVersion": "1.0",
        "metadata": {
            "generatedAt": datetime.now(UTC).isoformat(),
            "source": "Azure Databricks Gold",
            "catalog": catalog,
            "schema": gold_schema,
            "businessWindow": {
                "start": kpis["window_start"],
                "end": kpis["window_end"],
                "label": (
                    f"{kpis['window_start']} — {kpis['window_end']}"
                    if kpis["window_start"] and kpis["window_end"]
                    else "No sales observations"
                ),
            },
            "goldUpdatedAt": kpis["gold_updated_at"],
            "streamUpdatedAt": conversion["stream_updated_at"],
            "lastSuccessfulRunAt": last_successful_run,
            "queryVersion": "stage09-v2",
            "status": "verified",
        },
        "kpis": {
            "revenue": as_float(kpis["revenue"]),
            "orders": as_int(kpis["orders"]),
            "units": as_int(kpis["units"]),
            "averageOrderValue": as_float(kpis["average_order_value"]),
            "productViews": views,
            "purchases": purchases,
            # Kept for schema compatibility; this is an event ratio, not buyer conversion.
            "conversionRate": round(purchases / views, 4) if views else None,
        },
        "dailySales": [
            {
                "date": row["date"],
                "orders": as_int(row["orders"]),
                "units": as_int(row["units"]),
                "revenue": as_float(row["revenue"]),
                "averageOrderValue": as_float(row["average_order_value"]),
            }
            for row in daily_sales
        ],
        "countrySales": [
            {
                "country": str(row["country"] or "Unknown"),
                "orders": as_int(row["orders"]),
                "revenue": as_float(row["revenue"]),
            }
            for row in country_sales
        ],
        "topProducts": [
            {
                "productId": str(row["product_id"]),
                "units": as_int(row["units"]),
                "revenue": as_float(row["revenue"]),
            }
            for row in top_products
        ],
        "topCustomers": [
            {
                "customerId": str(row["customer_id"]),
                "country": str(row["country"] or "Unknown"),
                "orders": as_int(row["orders"]),
                "lifetimeValue": as_float(row["lifetime_value"]),
            }
            for row in top_customers
        ],
        "inventory": {
            "healthy": as_int(inventory_summary["healthy"]),
            "stale": as_int(inventory_summary["stale"]),
            "unknown": as_int(inventory_summary["unknown"]),
            "products": [
                {
                    "productId": str(row["product_id"]),
                    "unitsUpdated": as_int(row["units_updated"]),
                    "lastUpdate": row["last_update"],
                    "freshnessMinutes": (
                        as_int(row["freshness_minutes"])
                        if row["freshness_minutes"] is not None
                        else None
                    ),
                    "status": str(row["status"]),
                }
                for row in inventory_products
            ],
        },
        "eventRate": [
            {"minute": row["minute"], "events": as_int(row["events"])} for row in event_rate
        ],
        "reconciliation": {
            "checksPassed": reconciliation["checks_passed"],
            "checksTotal": reconciliation["checks_total"],
            "silverCustomers": as_int(reconciliation["silver_customers"]),
            "goldCustomers": as_int(reconciliation["gold_customers"]),
            "silverProducts": as_int(reconciliation["silver_products"]),
            "goldProducts": as_int(reconciliation["gold_products"]),
            "silverOrderItems": as_int(reconciliation["silver_order_items"]),
            "goldOrderItems": as_int(reconciliation["gold_order_items"]),
            "silverRevenue": as_float(reconciliation["silver_revenue"]),
            "goldRevenue": as_float(reconciliation["gold_revenue"]),
            "dailyRevenue": as_float(reconciliation["daily_revenue"]),
        },
    }


def write_snapshot(snapshot: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix="dashboard-",
            suffix=".json",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(snapshot, handle, indent=2, sort_keys=False, allow_nan=False)
            handle.write("\n")
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a validated Azure Gold BI snapshot.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bi-dashboard/public/data/dashboard.json"),
    )
    parser.add_argument(
        "--host",
        default=os.getenv(
            "RETAILPULSE_DATABRICKS_HOST",
            "adb-7405605234206971.11.azuredatabricks.net",
        ),
    )
    parser.add_argument(
        "--http-path",
        default=os.getenv(
            "RETAILPULSE_DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/74d4ebde2c184d68"
        ),
    )
    parser.add_argument(
        "--catalog",
        default=os.getenv("RETAILPULSE_DBT_CATALOG", "dbw_retailpulse_dev_rp999"),
    )
    parser.add_argument(
        "--gold-schema",
        default=os.getenv("RETAILPULSE_DBT_SCHEMA", "retailpulse_gold"),
    )
    parser.add_argument(
        "--silver-schema",
        default=os.getenv("RETAILPULSE_DBT_SOURCE_SCHEMA", "retailpulse_silver"),
    )
    parser.add_argument("--ops-schema", default="retailpulse_ops")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.getenv("DATABRICKS_TOKEN")
    if not token:
        raise SystemExit("DATABRICKS_TOKEN is required; use the attended Stage 9 runner.")

    from databricks import sql

    with (
        sql.connect(
            server_hostname=args.host,
            http_path=args.http_path,
            access_token=token,
            catalog=args.catalog,
            schema=args.gold_schema,
        ) as connection,
        connection.cursor() as cursor,
    ):
        snapshot = build_snapshot(
            cursor,
            catalog=args.catalog,
            gold_schema=args.gold_schema,
            silver_schema=args.silver_schema,
            ops_schema=args.ops_schema,
        )
    write_snapshot(snapshot, args.output)
    print(
        json.dumps(
            {
                "status": "STAGE9_SNAPSHOT_VERIFIED",
                "output": str(args.output),
                "generated_at": snapshot["metadata"]["generatedAt"],
                "reconciliation": snapshot["reconciliation"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
