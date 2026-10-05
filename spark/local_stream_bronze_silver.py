from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from delta import configure_spark_with_delta_pip
from delta.tables import DeltaTable
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from retailpulse.spark_contract import classify_events, read_contract_source

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
    # The v2 plan removes the old stateful deduplication operator. A new
    # checkpoint avoids attempting to restore incompatible legacy state.
    parser.add_argument("--checkpoint-namespace", default="local-contract-v2")
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
        .config("spark.sql.session.timeZone", "UTC")
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
        .withColumn("ingestion_timestamp", F.current_timestamp())
    )

    target_path = f"{base_path}/silver/events"
    existing_price_type = (
        spark.read.format("delta").load(target_path).schema["price"].dataType
        if DeltaTable.isDeltaTable(spark, target_path)
        else None
    )
    parsed = classify_events(raw, read_contract_source(), price_type=existing_price_type)
    invalid = parsed.filter(F.col("error_type").isNotNull())
    # Lateness is a business classification against ingestion time; no stateful
    # watermark deduplication may silently discard source rows before quarantine.
    valid = parsed.filter(F.col("error_type").isNull())

    def bounded_trigger(writer):
        if args.trigger_mode == "available-now":
            return writer.trigger(availableNow=True)
        return writer.trigger(processingTime="10 seconds")

    bronze_query = (
        bounded_trigger(
            raw.writeStream.format("delta")
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
                "topic",
                "partition",
                "offset",
                "kafka_timestamp",
                "ingestion_timestamp",
                "error_type",
                "error_message",
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
            "schema_version",
            "topic",
            "partition",
            "offset",
            "kafka_timestamp",
            "ingestion_timestamp",
        ]
        deduplicated = batch_df.select(*columns).dropDuplicates(["event_id"])
        batch_rows = deduplicated.count()
        target_exists = DeltaTable.isDeltaTable(spark, target_path)
        print(
            "STAGE3_SILVER_BATCH "
            f"batch_id={_batch_id} rows={batch_rows} target_exists={target_exists}"
        )
        if target_exists:
            (
                DeltaTable.forPath(spark, target_path)
                .alias("target")
                .merge(deduplicated.alias("source"), "target.event_id = source.event_id")
                .withSchemaEvolution()
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
        deadline = time.monotonic() + (args.max_runtime_minutes * 60)
        if args.trigger_mode == "available-now":
            for query in queries:
                query.awaitTermination(max(0.1, deadline - time.monotonic()))
        else:
            while any(query.isActive for query in queries) and time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                active = next(query for query in queries if query.isActive)
                active.awaitTermination(min(10.0, remaining))

        if any(query.isActive for query in queries):
            raise TimeoutError("local Spark stream exceeded --max-runtime-minutes")

        silver_path = f"{base_path}/silver/events"
        history = [
            {
                "version": row["version"],
                "operation": row["operation"],
                "operation_metrics": dict(row["operationMetrics"] or {}),
            }
            for row in (
                DeltaTable.forPath(spark, silver_path)
                .history(5)
                .select("version", "operation", "operationMetrics")
                .collect()
            )
        ]
        summary = {
            "trigger_mode": args.trigger_mode,
            "checkpoint_namespace": args.checkpoint_namespace,
            "bronze_rows": spark.read.format("delta").load(f"{base_path}/bronze/events").count(),
            "silver_rows": spark.read.format("delta").load(silver_path).count(),
            "quarantine_rows": (
                spark.read.format("delta").load(f"{base_path}/quarantine/events").count()
            ),
            "checkpoints_present": all(
                (
                    args.base_path.resolve() / "checkpoints" / args.checkpoint_namespace / name
                ).exists()
                for name in ("bronze_events", "quarantine_events", "silver_events")
            ),
            "silver_history": history,
        }
        print(f"STAGE3_LOCAL_SPARK_OK {json.dumps(summary, sort_keys=True)}")
    finally:
        for query in queries:
            if query.isActive:
                query.stop()
        spark.stop()


if __name__ == "__main__":
    main()
