# Databricks notebook source
import time

from delta.tables import DeltaTable
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

dbutils.widgets.text("kafka_bootstrap_servers", "EVENTHUB.servicebus.windows.net:9093")
dbutils.widgets.text("base_path", "abfss://retailpulse@ACCOUNT.dfs.core.windows.net")
dbutils.widgets.dropdown("trigger_mode", "available_now", ["available_now", "processing_time"])
dbutils.widgets.text("max_runtime_minutes", "30")
dbutils.widgets.text("max_offsets_per_trigger", "50000")
dbutils.widgets.text("checkpoint_namespace", "azure-demo")
bootstrap = dbutils.widgets.get("kafka_bootstrap_servers")
base_path = dbutils.widgets.get("base_path")
trigger_mode = dbutils.widgets.get("trigger_mode")
max_runtime_minutes = int(dbutils.widgets.get("max_runtime_minutes"))
max_offsets_per_trigger = int(dbutils.widgets.get("max_offsets_per_trigger"))
checkpoint_namespace = dbutils.widgets.get("checkpoint_namespace")

if not 1 <= max_runtime_minutes <= 30:
    raise ValueError("max_runtime_minutes must be between 1 and 30")
if max_offsets_per_trigger < 1:
    raise ValueError("max_offsets_per_trigger must be positive")
if not checkpoint_namespace.replace("-", "").replace("_", "").isalnum():
    raise ValueError(
        "checkpoint_namespace may contain only letters, numbers, hyphens, and underscores"
    )

checkpoint_root = f"{base_path}/checkpoints/{checkpoint_namespace}"

event_schema = StructType(
    [
        StructField("event_id", StringType(), False),
        StructField("event_type", StringType(), False),
        StructField("customer_id", StringType()),
        StructField("product_id", StringType()),
        StructField("order_id", StringType()),
        StructField("quantity", IntegerType()),
        StructField("price", DecimalType(12, 2)),
        StructField("country", StringType()),
        StructField("query", StringType()),
        StructField("event_timestamp", TimestampType(), False),
        StructField("schema_version", IntegerType(), False),
    ]
)

raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", bootstrap)
    .option("subscribe", "customer-events,order-events,inventory-events")
    .option("startingOffsets", "earliest")
    .option("maxOffsetsPerTrigger", max_offsets_per_trigger)
    .option("failOnDataLoss", "true")
    .load()
    .selectExpr(
        "CAST(value AS STRING) raw_payload",
        "topic",
        "partition",
        "offset",
        "timestamp kafka_timestamp",
    )
)


def bounded_trigger(writer):
    if trigger_mode == "available_now":
        return writer.trigger(availableNow=True)
    return writer.trigger(processingTime="10 seconds")

bronze_query = (
    bounded_trigger(
        raw.withColumn("ingestion_timestamp", F.current_timestamp())
        .writeStream.format("delta")
        .option("checkpointLocation", f"{checkpoint_root}/bronze_events")
        .outputMode("append")
    )
    .queryName(f"retailpulse_bronze_{checkpoint_namespace}")
    .start(f"{base_path}/bronze/events")
)

parsed = raw.withColumn("event", F.from_json("raw_payload", event_schema)).select(
    "raw_payload", "topic", "partition", "offset", "kafka_timestamp", "event.*"
)
invalid = parsed.filter(F.col("event_id").isNull())
valid = (
    parsed.filter(F.col("event_id").isNotNull())
    .withWatermark("event_timestamp", "30 minutes")
    .dropDuplicates(["event_id"])
)

quarantine_query = (
    bounded_trigger(
        invalid.select(
            "event_id",
            "raw_payload",
            F.lit("SCHEMA_VALIDATION").alias("error_type"),
            F.lit("Payload does not conform to schema version 1").alias("error_message"),
            F.current_timestamp().alias("timestamp"),
        )
        .writeStream.format("delta")
        .option("checkpointLocation", f"{checkpoint_root}/quarantine_events")
        .outputMode("append")
    )
    .queryName(f"retailpulse_quarantine_{checkpoint_namespace}")
    .start(f"{base_path}/quarantine/events")
)


def merge_silver(batch_df, batch_id: int) -> None:
    target_path = f"{base_path}/silver/events"
    deduplicated = batch_df.dropDuplicates(["event_id"])
    if DeltaTable.isDeltaTable(spark, target_path):
        target = DeltaTable.forPath(spark, target_path)
        (
            target.alias("target")
            .merge(deduplicated.alias("source"), "target.event_id = source.event_id")
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        deduplicated.write.format("delta").mode("overwrite").save(target_path)


silver_query = (
    bounded_trigger(
        valid.writeStream.foreachBatch(merge_silver).option(
            "checkpointLocation", f"{checkpoint_root}/silver_events"
        )
    )
    .queryName(f"retailpulse_silver_{checkpoint_namespace}")
    .start()
)

queries = [bronze_query, quarantine_query, silver_query]
if trigger_mode == "available_now":
    for query in queries:
        query.awaitTermination()
else:
    deadline = time.monotonic() + (max_runtime_minutes * 60)
    try:
        while any(query.isActive for query in queries) and time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            active = next(query for query in queries if query.isActive)
            active.awaitTermination(min(10.0, remaining))
    finally:
        for query in queries:
            if query.isActive:
                query.stop()
        for query in queries:
            query.awaitTermination()
