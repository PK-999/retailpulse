# Databricks notebook source
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType, IntegerType, StringType, StructField, StructType

# Configure these as Databricks job parameters.
dbutils.widgets.text("landing_path", "abfss://retailpulse@ACCOUNT.dfs.core.windows.net/landing/uci")
dbutils.widgets.text("base_path", "abfss://retailpulse@ACCOUNT.dfs.core.windows.net")
dbutils.widgets.text("run_id", "manual")

landing_path = dbutils.widgets.get("landing_path")
base_path = dbutils.widgets.get("base_path")
run_id = dbutils.widgets.get("run_id")

datasets = {
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

for name, schema in datasets.items():
    source = f"{landing_path}/{name}.jsonl"
    bronze = f"{base_path}/bronze/{name}"
    silver = f"{base_path}/silver/{name}"
    raw = (
        spark.read.schema(schema)
        .json(source)
        .withColumn("source_file", F.input_file_name())
        .withColumn("ingestion_timestamp", F.current_timestamp())
        .withColumn("pipeline_run_id", F.lit(run_id))
    )
    raw.write.format("delta").mode("append").save(bronze)

    key = {"customers": "customer_id", "products": "product_id", "orders": "order_id"}.get(name)
    clean = raw.dropDuplicates([key] if key else ["order_id", "product_id"])
    if name == "orders":
        clean = clean.withColumn("order_timestamp", F.to_timestamp("order_timestamp"))
    if name == "order_items":
        valid = (F.col("quantity") > 0) & (F.col("unit_price") >= 0)
        clean.filter(~valid).write.format("delta").mode("append").save(
            f"{base_path}/quarantine/{name}"
        )
        clean = clean.filter(valid)
    clean.write.format("delta").mode("append").option("mergeSchema", "true").save(silver)
