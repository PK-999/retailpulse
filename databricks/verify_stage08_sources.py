# Databricks notebook source
import json
import re

from pyspark.sql import functions as F

dbutils.widgets.text("catalog_name", "")
catalog_name = dbutils.widgets.get("catalog_name")

if not re.fullmatch(r"[A-Za-z0-9_]+", catalog_name):
    raise ValueError("catalog_name contains unsupported characters")

silver_schema = f"`{catalog_name}`.`retailpulse_silver`"
ops_schema = f"`{catalog_name}`.`retailpulse_ops`"
expected_tables = {
    "customers": 1,
    "products": 1,
    "orders": 1,
    "order_items": 1,
    "streaming_events": 1,
}

counts = {}
for table_name, minimum_rows in expected_tables.items():
    relation = f"{silver_schema}.`{table_name}`"
    if not spark.catalog.tableExists(relation.replace("`", "")):
        raise RuntimeError(f"Required Silver table is missing: {relation}")
    count = spark.table(relation).count()
    if count < minimum_rows:
        raise RuntimeError(f"Required Silver table is empty: {relation}")
    counts[table_name] = count

orphan_items = (
    spark.table(f"{silver_schema}.`order_items`").alias("items")
    .join(
        spark.table(f"{silver_schema}.`orders`").select("order_id").alias("orders"),
        "order_id",
        "left_anti",
    )
    .count()
)
if orphan_items != 0:
    raise RuntimeError(f"Silver contains {orphan_items} order items without an order")

historical_successes = (
    spark.table(f"{ops_schema}.`historical_batch_runs`")
    .filter(F.col("status") == "SUCCESS")
    .count()
)
streaming_batches = spark.table(f"{ops_schema}.`streaming_batch_runs`").count()
if historical_successes < 2 or streaming_batches < 1:
    raise RuntimeError(
        "Stage 8 requires two successful historical deliveries and streaming audit evidence"
    )

dbutils.notebook.exit(
    json.dumps(
        {
            "status": "STAGE8_SILVER_READY",
            "counts": counts,
            "orphan_order_items": orphan_items,
            "historical_successes": historical_successes,
            "streaming_batches": streaming_batches,
        },
        sort_keys=True,
    )
)
