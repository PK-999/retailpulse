# Databricks notebook source
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
bootstrap = dbutils.widgets.get("kafka_bootstrap_servers")
base_path = dbutils.widgets.get("base_path")

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
    .option("startingOffsets", "latest")
    .load()
    .selectExpr(
        "CAST(value AS STRING) raw_payload",
        "topic",
        "partition",
        "offset",
        "timestamp kafka_timestamp",
    )
)

bronze_query = (
    raw.withColumn("ingestion_timestamp", F.current_timestamp())
    .writeStream.format("delta")
    .option("checkpointLocation", f"{base_path}/checkpoints/bronze_events")
    .outputMode("append")
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
    invalid.select(
        "event_id",
        "raw_payload",
        F.lit("SCHEMA_VALIDATION").alias("error_type"),
        F.lit("Payload does not conform to schema version 1").alias("error_message"),
        F.current_timestamp().alias("timestamp"),
    )
    .writeStream.format("delta")
    .option("checkpointLocation", f"{base_path}/checkpoints/quarantine_events")
    .outputMode("append")
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
    valid.writeStream.foreachBatch(merge_silver)
    .option("checkpointLocation", f"{base_path}/checkpoints/silver_events")
    .start()
)

spark.streams.awaitAnyTermination()
