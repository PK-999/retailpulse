from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from delta import configure_spark_with_delta_pip
from delta.tables import DeltaTable
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

SPARK_VERSION = "4.0.4"
KAFKA_PACKAGE = f"org.apache.spark:spark-sql-kafka-0-10_2.13:{SPARK_VERSION}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the bounded local Kafka-to-Delta stream.")
    parser.add_argument("--bootstrap-servers", default="localhost:19092")
    parser.add_argument("--base-path", type=Path, default=Path("data/spark"))
    parser.add_argument(
        "--trigger-mode", choices=("available-now", "processing-time"), default="available-now"
    )
    parser.add_argument("--max-runtime-minutes", type=int, default=30)
    parser.add_argument("--max-offsets-per-trigger", type=int, default=50_000)
    parser.add_argument("--checkpoint-namespace", default="local-dev")
    return parser.parse_args()


def build_spark() -> SparkSession:
    builder = (
        SparkSession.builder.master("local[*]")
        .appName("RetailPulseLocalStreaming")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.sql.shuffle.partitions", "4")
    )
    return configure_spark_with_delta_pip(builder, extra_packages=[KAFKA_PACKAGE]).getOrCreate()


def main() -> None:
    args = parse_args()
    if not 1 <= args.max_runtime_minutes <= 30:
        raise SystemExit("--max-runtime-minutes must be between 1 and 30")
    if args.max_offsets_per_trigger < 1:
        raise SystemExit("--max-offsets-per-trigger must be positive")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.checkpoint_namespace):
        raise SystemExit("--checkpoint-namespace contains unsupported characters")

    spark = build_spark()
    base_path = args.base_path.resolve().as_uri()
    checkpoint_root = f"{base_path}/checkpoints/{args.checkpoint_namespace}"
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
        .option("kafka.bootstrap.servers", args.bootstrap_servers)
        .option("subscribe", "customer-events,order-events,inventory-events")
        .option("startingOffsets", "earliest")
        .option("maxOffsetsPerTrigger", args.max_offsets_per_trigger)
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

    parsed = raw.withColumn("event", F.from_json("raw_payload", event_schema)).select(
        "raw_payload", "topic", "partition", "offset", "kafka_timestamp", "event.*"
    )
    invalid = parsed.filter(F.col("event_id").isNull())
    valid = (
        parsed.filter(F.col("event_id").isNotNull())
        .withWatermark("event_timestamp", "30 minutes")
        .dropDuplicates(["event_id"])
    )

    def bounded_trigger(writer):
        if args.trigger_mode == "available-now":
            return writer.trigger(availableNow=True)
        return writer.trigger(processingTime="10 seconds")

    bronze_query = (
        bounded_trigger(
            raw.withColumn("ingestion_timestamp", F.current_timestamp())
            .writeStream.format("delta")
            .option("checkpointLocation", f"{checkpoint_root}/bronze_events")
            .outputMode("append")
        )
        .queryName(f"retailpulse_bronze_{args.checkpoint_namespace}")
        .start(f"{base_path}/bronze/events")
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
        .queryName(f"retailpulse_quarantine_{args.checkpoint_namespace}")
        .start(f"{base_path}/quarantine/events")
    )

    def merge_silver(batch_df, _batch_id: int) -> None:
        target_path = f"{base_path}/silver/events"
        columns = [
            "event_id",
            "event_type",
            "customer_id",
            "product_id",
            "order_id",
            "quantity",
            "price",
            "country",
            "query",
            "event_timestamp",
            "topic",
            "partition",
            "offset",
            "kafka_timestamp",
        ]
        deduplicated = batch_df.select(*columns).dropDuplicates(["event_id"])
        if DeltaTable.isDeltaTable(spark, target_path):
            (
                DeltaTable.forPath(spark, target_path)
                .alias("target")
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
        .queryName(f"retailpulse_silver_{args.checkpoint_namespace}")
        .start()
    )

    queries = [bronze_query, quarantine_query, silver_query]
    try:
        if args.trigger_mode == "available-now":
            for query in queries:
                query.awaitTermination()
        else:
            deadline = time.monotonic() + (args.max_runtime_minutes * 60)
            while any(query.isActive for query in queries) and time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                active = next(query for query in queries if query.isActive)
                active.awaitTermination(min(10.0, remaining))
    finally:
        for query in queries:
            if query.isActive:
                query.stop()
        spark.stop()


if __name__ == "__main__":
    main()
