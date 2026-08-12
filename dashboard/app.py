from __future__ import annotations

import json
import os
import sqlite3
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

connection = sqlite3.connect(database)
summary = pd.read_sql_query(
    """SELECT COUNT(*) orders, COALESCE(SUM(order_total), 0) revenue,
              COALESCE(AVG(order_total), 0) average_order_value
       FROM fact_orders""",
    connection,
).iloc[0]
views = pd.read_sql_query(
    "SELECT COUNT(*) count FROM silver_events WHERE event_type = 'product_view'", connection
).iloc[0, 0]
purchases = pd.read_sql_query(
    "SELECT COUNT(*) count FROM silver_events WHERE event_type = 'purchase'", connection
).iloc[0, 0]

columns = st.columns(5)
columns[0].metric("Revenue", f"£{summary.revenue:,.2f}")
columns[1].metric("Orders", f"{int(summary.orders):,}")
columns[2].metric("Average order value", f"£{summary.average_order_value:,.2f}")
columns[3].metric("Product views", f"{views:,}")
columns[4].metric("Conversion rate", f"{purchases / views:.1%}" if views else "n/a")

sales = pd.read_sql_query("SELECT * FROM daily_sales ORDER BY order_date", connection)
left, right = st.columns(2)
with left:
    st.subheader("Daily revenue")
    if len(sales) == 1:
        st.bar_chart(sales, x="order_date", y="revenue")
    else:
        st.line_chart(sales, x="order_date", y="revenue")
with right:
    st.subheader("Sales by country")
    countries = pd.read_sql_query(
        """SELECT country, ROUND(SUM(order_total), 2) revenue
           FROM fact_orders GROUP BY country ORDER BY revenue DESC""",
        connection,
    )
    st.bar_chart(countries, x="country", y="revenue")

top_products, top_customers = st.columns(2)
with top_products:
    st.subheader("Top products")
    products = pd.read_sql_query(
        """SELECT product_id, SUM(quantity) units,
                  ROUND(SUM(quantity * price), 2) revenue
           FROM silver_events
           WHERE event_type = 'purchase' AND product_id IS NOT NULL
           GROUP BY product_id ORDER BY revenue DESC LIMIT 10""",
        connection,
    )
    st.bar_chart(products, x="product_id", y="revenue")
with top_customers:
    st.subheader("Top customers")
    customers = pd.read_sql_query(
        """SELECT customer_id, ROUND(SUM(order_total), 2) lifetime_value
           FROM fact_orders WHERE customer_id IS NOT NULL
           GROUP BY customer_id ORDER BY lifetime_value DESC LIMIT 10""",
        connection,
    )
    st.bar_chart(customers, x="customer_id", y="lifetime_value")

streaming, inventory = st.columns(2)
with streaming:
    st.subheader("Streaming events per minute")
    events_per_minute = pd.read_sql_query(
        """SELECT substr(ingestion_timestamp, 1, 16) minute, COUNT(*) events
           FROM silver_events GROUP BY minute ORDER BY minute""",
        connection,
    )
    st.line_chart(events_per_minute, x="minute", y="events")
with inventory:
    st.subheader("Inventory freshness")
    inventory_updates = pd.read_sql_query(
        """SELECT product_id, SUM(quantity) units_updated,
                  MAX(event_timestamp) last_update
           FROM silver_events WHERE event_type = 'inventory_update'
           GROUP BY product_id ORDER BY last_update DESC""",
        connection,
    )
    st.dataframe(inventory_updates, width="stretch", hide_index=True)

st.subheader("Recent pipeline runs")
runs = pd.read_sql_query(
    """SELECT start_time, status, records_read, records_written, records_rejected,
              records_duplicate, records_late, duration_seconds
       FROM pipeline_run_log ORDER BY start_time DESC LIMIT 20""",
    connection,
)
st.dataframe(runs, width="stretch", hide_index=True)

metrics_file = data_dir / "metrics" / "latest.json"
if metrics_file.exists():
    state = json.loads(metrics_file.read_text(encoding="utf-8"))
    if state["alerts"]:
        st.error(f"{len(state['alerts'])} active data-quality alert(s)")
        st.dataframe(state["alerts"], width="stretch", hide_index=True)
connection.close()
