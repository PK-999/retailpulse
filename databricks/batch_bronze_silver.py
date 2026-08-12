# Databricks notebook source
import json
import re
import time
from decimal import Decimal

from delta.tables import DeltaTable
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType, IntegerType, StringType, StructField, StructType

dbutils.widgets.text("landing_path", "")
dbutils.widgets.text("base_path", "")
dbutils.widgets.text("pipeline_run_id", "")
dbutils.widgets.text("catalog_name", "")
dbutils.widgets.text("profile_name", "azure")
dbutils.widgets.text("max_customers", "1000")
dbutils.widgets.text("max_products", "250")
dbutils.widgets.text("max_orders", "5000")
dbutils.widgets.text("max_order_items", "25000")
dbutils.widgets.text("inject_invalid_item", "false")

landing_path = dbutils.widgets.get("landing_path").rstrip("/")
base_path = dbutils.widgets.get("base_path").rstrip("/")
pipeline_run_id = dbutils.widgets.get("pipeline_run_id")
catalog_name = dbutils.widgets.get("catalog_name")
profile_name = dbutils.widgets.get("profile_name")
max_customers = int(dbutils.widgets.get("max_customers"))
max_products = int(dbutils.widgets.get("max_products"))
max_orders = int(dbutils.widgets.get("max_orders"))
max_order_items = int(dbutils.widgets.get("max_order_items"))
inject_invalid_item = dbutils.widgets.get("inject_invalid_item").lower() == "true"

if profile_name != "azure":
    raise ValueError("Stage 6 accepts only the bounded azure profile")
if not re.fullmatch(r"[A-Za-z0-9_]+", catalog_name):
    raise ValueError("catalog_name contains unsupported characters")
if not re.fullmatch(r"[a-f0-9-]{36}", pipeline_run_id):
    raise ValueError("pipeline_run_id must be the Stage 5 ADF run UUID")
if pipeline_run_id not in landing_path:
    raise ValueError("landing_path must be scoped by pipeline_run_id")
if not base_path.startswith("abfss://retailpulse@"):
    raise ValueError("base_path must be the RetailPulse ADLS filesystem")
if (max_customers, max_products, max_orders, max_order_items) != (1000, 250, 5000, 25000):
    raise ValueError("Stage 6 volume caps must match config/azure.yml")

started_at = time.monotonic()
bronze_schema = "retailpulse_bronze"
silver_schema = "retailpulse_silver"
ops_schema = "retailpulse_ops"
for schema_name in (bronze_schema, silver_schema, ops_schema):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog_name}`.`{schema_name}`")

schemas = {
    "customers": StructType(
        [StructField("customer_id", StringType()), StructField("country", StringType())]
    ),
    "products": StructType(
        [
            StructField("product_id", StringType()),
            StructField("description", StringType()),
            StructField("unit_price", DecimalType(12, 2)),
        ]
    ),
    "orders": StructType(
        [
            StructField("order_id", StringType()),
            StructField("customer_id", StringType()),
            StructField("order_timestamp", StringType()),
            StructField("country", StringType()),
            StructField("is_cancelled", StringType()),
        ]
    ),
    "order_items": StructType(
        [
            StructField("order_id", StringType()),
            StructField("product_id", StringType()),
            StructField("quantity", IntegerType()),
            StructField("unit_price", DecimalType(12, 2)),
        ]
    ),
}
business_columns = {
    name: [field.name for field in schema.fields] for name, schema in schemas.items()
}


def read_source(name: str) -> DataFrame:
    return (
        spark.read.schema(schemas[name])
        .json(f"{landing_path}/{name}.jsonl")
        .select("*", F.col("_metadata.file_path").alias("source_file"))
    )


source_customers = read_source("customers")
source_products = read_source("products")
source_orders = read_source("orders")
source_items = read_source("order_items")

candidate_customers = source_customers.orderBy("customer_id").limit(max_customers)
candidate_products = source_products.orderBy("product_id").limit(max_products)
candidate_orders = (
    source_orders.alias("orders")
    .join(
        candidate_customers.select("customer_id").alias("customers"),
        F.col("orders.customer_id") == F.col("customers.customer_id"),
        "inner",
    )
    .select("orders.*")
    .orderBy("order_id")
    .limit(max_orders)
)
selected_items = (
    source_items.alias("items")
    .join(candidate_orders.select("order_id").alias("orders"), "order_id", "inner")
    .join(candidate_products.select("product_id").alias("products"), "product_id", "inner")
    .select("items.*")
    .orderBy("order_id", "product_id", "quantity", "unit_price")
    .limit(max_order_items)
)
selected_order_ids = selected_items.select("order_id").distinct()
selected_product_ids = selected_items.select("product_id").distinct()
selected_orders = candidate_orders.join(selected_order_ids, "order_id", "inner")
selected_customer_ids = (
    selected_orders.select("customer_id").where("customer_id IS NOT NULL").distinct()
)
selected_customers = candidate_customers.join(selected_customer_ids, "customer_id", "inner")
selected_products = candidate_products.join(selected_product_ids, "product_id", "inner")

selected = {
    "customers": selected_customers,
    "products": selected_products,
    "orders": selected_orders,
    "order_items": selected_items,
}

if inject_invalid_item:
    invalid = spark.createDataFrame(
        [
            (
                f"STAGE06-INVALID-{pipeline_run_id}",
                "STAGE06-INVALID",
                -1,
                Decimal("1.00"),
            )
        ],
        "order_id STRING, product_id STRING, quantity INT, unit_price DECIMAL(12,2)",
    ).withColumn("source_file", F.lit("stage06://injected-invalid-order-item"))
    selected["order_items"] = selected["order_items"].unionByName(invalid)


def enrich(name: str, frame: DataFrame) -> DataFrame:
    columns = business_columns[name]
    return (
        frame.select(*columns, "source_file")
        .withColumn("ingestion_timestamp", F.current_timestamp())
        .withColumn("ingestion_date", F.current_date())
        .withColumn("pipeline_run_id", F.lit(pipeline_run_id))
        .withColumn("dataset_name", F.lit(name))
        .withColumn("_record_hash", F.sha2(F.to_json(F.struct(*columns)), 256))
    )


raw = {name: enrich(name, frame) for name, frame in selected.items()}
raw["orders"] = raw["orders"].withColumn(
    "parsed_order_timestamp", F.to_timestamp("order_timestamp", "yyyy-MM-dd HH:mm:ss")
)

valid_conditions = {
    "customers": F.col("customer_id").isNotNull() & (F.trim("customer_id") != ""),
    "products": (
        F.col("product_id").isNotNull()
        & (F.trim("product_id") != "")
        & F.col("unit_price").isNotNull()
        & (F.col("unit_price") >= 0)
    ),
    "orders": (
        F.col("order_id").isNotNull()
        & (F.trim("order_id") != "")
        & F.col("parsed_order_timestamp").isNotNull()
        & F.col("is_cancelled").isin("true", "false")
    ),
    "order_items": (
        F.col("order_id").isNotNull()
        & (F.trim("order_id") != "")
        & F.col("product_id").isNotNull()
        & (F.trim("product_id") != "")
        & F.col("quantity").isNotNull()
        & (F.col("quantity") > 0)
        & F.col("unit_price").isNotNull()
        & (F.col("unit_price") >= 0)
    ),
}
error_messages = {
    "customers": "customer_id is required",
    "products": "product_id is required and unit_price must be non-negative",
    "orders": "order_id, parseable timestamp, and true/false cancellation flag are required",
    "order_items": "order/product IDs are required; quantity > 0 and unit_price >= 0",
}


def ensure_external_table(frame: DataFrame, table_name: str, path: str) -> None:
    if not DeltaTable.isDeltaTable(spark, path):
        frame.limit(0).write.format("delta").mode("ignore").save(path)
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table_name} USING DELTA LOCATION '{path}'")


def delta_metrics(table_name: str) -> dict[str, str]:
    row = spark.sql(f"DESCRIBE HISTORY {table_name} LIMIT 1").select(
        "version", "operation", "operationMetrics"
    ).first()
    return {
        "version": int(row["version"]),
        "operation": row["operation"],
        **{key: value for key, value in dict(row["operationMetrics"] or {}).items()},
    }


def merge_insert_only(
    frame: DataFrame, table_name: str, path: str, condition: str
) -> dict[str, str]:
    ensure_external_table(frame, table_name, path)
    dataset_name = table_name.replace("`", "").split(".")[-1]
    view_name = f"stage06_{dataset_name}_{pipeline_run_id.replace('-', '_')}"
    frame.createOrReplaceTempView(view_name)
    spark.sql(
        f"MERGE INTO {table_name} AS target USING {view_name} AS source ON {condition} "
        "WHEN NOT MATCHED THEN INSERT *"
    )
    return delta_metrics(table_name)


def merge_current(
    frame: DataFrame, table_name: str, path: str, key_condition: str
) -> dict[str, str]:
    ensure_external_table(frame, table_name, path)
    dataset_name = table_name.replace("`", "").split(".")[-1]
    view_name = f"stage06_{dataset_name}_{pipeline_run_id.replace('-', '_')}"
    frame.createOrReplaceTempView(view_name)
    spark.sql(
        f"MERGE INTO {table_name} AS target USING {view_name} AS source ON {key_condition} "
        "WHEN MATCHED AND target._record_hash <> source._record_hash THEN UPDATE SET * "
        "WHEN NOT MATCHED THEN INSERT *"
    )
    return delta_metrics(table_name)


results = {}
quarantine_frames = []
for name in schemas:
    input_rows = raw[name].count()
    is_valid = F.coalesce(valid_conditions[name], F.lit(False))
    valid = raw[name].filter(is_valid)
    invalid = raw[name].filter(~is_valid)
    valid_rows = valid.count()
    rejected_rows = input_rows - valid_rows

    quarantine_frames.append(
        invalid.select(
            "pipeline_run_id",
            "dataset_name",
            "source_file",
            "ingestion_timestamp",
            "_record_hash",
            F.lit("BUSINESS_RULE").alias("error_type"),
            F.lit(error_messages[name]).alias("error_message"),
            F.to_json(F.struct(*business_columns[name])).alias("raw_record_json"),
        )
    )

    bronze_table = f"`{catalog_name}`.`{bronze_schema}`.`{name}`"
    silver_table = f"`{catalog_name}`.`{silver_schema}`.`{name}`"
    bronze_path = f"{base_path}/bronze/historical/{name}"
    silver_path = f"{base_path}/silver/historical/{name}"
    bronze_history = merge_insert_only(
        raw[name],
        bronze_table,
        bronze_path,
        "target.pipeline_run_id = source.pipeline_run_id "
        "AND target._record_hash = source._record_hash",
    )

    silver_source = valid.dropDuplicates(
        [
            {"customers": "customer_id", "products": "product_id", "orders": "order_id"}.get(
                name, "_record_hash"
            )
        ]
    )
    if name == "orders":
        silver_source = silver_source.drop("order_timestamp").withColumnRenamed(
            "parsed_order_timestamp", "order_timestamp"
        )
    if name == "order_items":
        silver_history = merge_insert_only(
            silver_source,
            silver_table,
            silver_path,
            "target._record_hash = source._record_hash",
        )
    else:
        key = {"customers": "customer_id", "products": "product_id", "orders": "order_id"}[name]
        silver_history = merge_current(
            silver_source,
            silver_table,
            silver_path,
            f"target.{key} = source.{key}",
        )

    results[name] = {
        "input_rows": input_rows,
        "valid_rows": valid_rows,
        "rejected_rows": rejected_rows,
        "bronze_total": spark.table(bronze_table).count(),
        "silver_total": spark.table(silver_table).count(),
        "bronze_history": bronze_history,
        "silver_history": silver_history,
    }

quarantine = quarantine_frames[0]
for frame in quarantine_frames[1:]:
    quarantine = quarantine.unionByName(frame)
quarantine_table = f"`{catalog_name}`.`{ops_schema}`.`historical_quarantine`"
quarantine_path = f"{base_path}/quarantine/historical/records"
quarantine_history = merge_insert_only(
    quarantine,
    quarantine_table,
    quarantine_path,
    "target.pipeline_run_id = source.pipeline_run_id "
    "AND target.dataset_name = source.dataset_name "
    "AND target._record_hash = source._record_hash",
)

records_read = sum(result["input_rows"] for result in results.values())
records_rejected = sum(result["rejected_rows"] for result in results.values())
records_valid = sum(result["valid_rows"] for result in results.values())
duration_seconds = round(time.monotonic() - started_at, 3)
audit_record = spark.createDataFrame(
    [
        (
            pipeline_run_id,
            landing_path,
            profile_name,
            records_read,
            records_valid,
            records_rejected,
            duration_seconds,
            "SUCCESS",
            json.dumps(results, sort_keys=True),
        )
    ],
    "pipeline_run_id STRING, landing_path STRING, profile_name STRING, records_read LONG, "
    "records_valid LONG, records_rejected LONG, duration_seconds DOUBLE, status STRING, "
    "delta_metrics_json STRING",
).withColumn("completed_at", F.current_timestamp())
audit_table = f"`{catalog_name}`.`{ops_schema}`.`historical_batch_runs`"
audit_path = f"{base_path}/bronze/_audit/historical_batch_runs"
audit_history = merge_insert_only(
    audit_record,
    audit_table,
    audit_path,
    "target.pipeline_run_id = source.pipeline_run_id",
)

summary = {
    "status": "STAGE6_BATCH_OK",
    "pipeline_run_id": pipeline_run_id,
    "landing_path": landing_path,
    "profile_name": profile_name,
    "profile_caps": {
        "customers": max_customers,
        "products": max_products,
        "orders": max_orders,
        "order_items": max_order_items,
    },
    "inject_invalid_item": inject_invalid_item,
    "records_read": records_read,
    "records_valid": records_valid,
    "records_rejected": records_rejected,
    "duration_seconds": duration_seconds,
    "datasets": results,
    "quarantine_total": spark.table(quarantine_table).count(),
    "quarantine_history": quarantine_history,
    "audit_total": spark.table(audit_table).count(),
    "audit_history": audit_history,
    "tables": {
        "bronze_schema": f"{catalog_name}.{bronze_schema}",
        "silver_schema": f"{catalog_name}.{silver_schema}",
        "ops_schema": f"{catalog_name}.{ops_schema}",
    },
}
dbutils.notebook.exit(json.dumps(summary, sort_keys=True))
