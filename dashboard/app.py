from __future__ import annotations

import json
import os
import sqlite3
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

data_dir = Path(os.getenv("RETAILPULSE_DATA_DIR", "data"))
database = data_dir / "retailpulse.db"

st.set_page_config(page_title="RetailPulse", page_icon="📈", layout="wide")
st.title("RetailPulse Operations & Commerce")

if not database.exists():
    st.info("Run `retailpulse produce` and `retailpulse process` to create dashboard data.")
    st.stop()


def load_dashboard_data(database_path: Path) -> dict[str, pd.DataFrame]:
    queries = {
        "summary": """SELECT COUNT(*) orders, COALESCE(SUM(order_total), 0) revenue,
                      COALESCE(AVG(order_total), 0) average_order_value,
                      MIN(substr(order_timestamp, 1, 10)) window_start,
                      MAX(substr(order_timestamp, 1, 10)) window_end
                      FROM fact_orders""",
        "views": "SELECT COUNT(*) count FROM silver_events WHERE event_type = 'product_view'",
        "purchases": "SELECT COUNT(*) count FROM silver_events WHERE event_type = 'purchase'",
        "sales": "SELECT * FROM daily_sales ORDER BY order_date",
        "countries": """SELECT country, ROUND(SUM(order_total), 2) revenue
                        FROM fact_orders GROUP BY country ORDER BY revenue DESC, country""",
        "products": """SELECT product_id, SUM(quantity) units,
                       SUM(quantity * unit_price_cents(price)) / 100.0 revenue
                       FROM silver_events WHERE event_type = 'purchase' AND product_id IS NOT NULL
                       GROUP BY product_id ORDER BY revenue DESC, product_id LIMIT 10""",
        "customers": """SELECT customer_id, ROUND(SUM(order_total), 2) lifetime_value
                        FROM fact_orders WHERE customer_id IS NOT NULL
                        GROUP BY customer_id ORDER BY lifetime_value DESC, customer_id LIMIT 10""",
        "events": """SELECT substr(ingestion_timestamp, 1, 16) minute, COUNT(*) events
                     FROM silver_events GROUP BY minute ORDER BY minute""",
        "inventory": """SELECT product_id, SUM(quantity) units_updated,
                        MAX(event_timestamp) last_update
                        FROM silver_events WHERE event_type = 'inventory_update'
                        GROUP BY product_id ORDER BY last_update DESC, product_id""",
        "runs": """SELECT start_time, status, records_read, records_written, records_rejected,
                   records_duplicate, records_late, duration_seconds
                   FROM pipeline_run_log ORDER BY start_time DESC LIMIT 20""",
    }
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    connection.create_function(
        "unit_price_cents",
        1,
        lambda price: int(Decimal(price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100),
        deterministic=True,
    )
    try:
        return {name: pd.read_sql_query(query, connection) for name, query in queries.items()}
    finally:
        connection.close()


try:
    frames = load_dashboard_data(database)
except (sqlite3.Error, pd.errors.DatabaseError):
    st.error(
        "Dashboard data could not be read. Run `retailpulse process` "
        "to initialize or rebuild the local tables."
    )
    st.stop()

summary = frames["summary"].iloc[0]
views = int(frames["views"].iloc[0, 0])
purchases = int(frames["purchases"].iloc[0, 0])
window = (
    f"{summary.window_start} — {summary.window_end}" if summary.orders else "No sales observations"
)
st.caption(
    f"Local demo data · Business dates: {window}. "
    "Pipeline run timestamps below show when the data was processed."
)
st.caption(
    "Purchase and view events are independently sampled. "
    "The purchase/view ratio is not customer conversion and can exceed 100%."
)

columns = st.columns(5)
columns[0].metric("Revenue", f"£{summary.revenue:,.2f}")
columns[1].metric("Orders", f"{int(summary.orders):,}")
columns[2].metric("Average order value", f"£{summary.average_order_value:,.2f}")
columns[3].metric("Product views", f"{views:,}")
columns[4].metric("Purchase/view ratio", f"{purchases / views:.1%}" if views else "n/a")

sales = frames["sales"]
left, right = st.columns(2)
with left:
    st.subheader("Daily revenue")
    if len(sales) == 1:
        st.bar_chart(sales, x="order_date", y="revenue")
    else:
        st.line_chart(sales, x="order_date", y="revenue")
with right:
    st.subheader("Sales by country")
    countries = frames["countries"]
    st.bar_chart(countries, x="country", y="revenue")

top_products, top_customers = st.columns(2)
with top_products:
    st.subheader("Top products")
    products = frames["products"]
    st.bar_chart(products, x="product_id", y="revenue")
with top_customers:
    st.subheader("Top customers")
    customers = frames["customers"]
    st.bar_chart(customers, x="customer_id", y="lifetime_value")

streaming, inventory = st.columns(2)
with streaming:
    st.subheader("Streaming events per minute")
    events_per_minute = frames["events"]
    st.line_chart(events_per_minute, x="minute", y="events")
with inventory:
    st.subheader("Inventory freshness")
    inventory_updates = frames["inventory"]
    st.dataframe(inventory_updates, width="stretch", hide_index=True)

st.subheader("Recent pipeline runs")
runs = frames["runs"]
st.dataframe(runs, width="stretch", hide_index=True)

metrics_file = data_dir / "metrics" / "latest.json"
if metrics_file.exists():
    try:
        state = json.loads(metrics_file.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("alerts"), list):
            raise ValueError("Invalid metrics shape")
        alerts = state["alerts"]
        if not all(isinstance(alert, dict) for alert in alerts):
            raise ValueError("Invalid alerts")
    except (OSError, ValueError):
        st.warning(
            "Latest metrics could not be read. "
            "Re-run `retailpulse process` to regenerate the metrics file."
        )
    else:
        if alerts:
            st.error(f"{len(alerts)} active data-quality alert(s)")
            st.dataframe(alerts, width="stretch", hide_index=True)
