# Databricks notebook source
import json
import re
import time

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

dbutils.widgets.text("kafka_bootstrap_servers", "")
dbutils.widgets.text("base_path", "")
dbutils.widgets.text("catalog_name", "")
dbutils.widgets.text("secret_scope", "retailpulse-stage07")
dbutils.widgets.text("secret_key", "eventhubs-kafka-connection-string")
dbutils.widgets.dropdown("trigger_mode", "available_now", ["available_now"])
dbutils.widgets.text("max_runtime_minutes", "30")
dbutils.widgets.text("max_offsets_per_trigger", "5000")
dbutils.widgets.text("checkpoint_namespace", "")
dbutils.widgets.text("fail_after_committed_batch", "false")
dbutils.widgets.dropdown("starting_offsets", "earliest", ["earliest", "latest"])
dbutils.widgets.text("stream_run_id", "")

bootstrap = dbutils.widgets.get("kafka_bootstrap_servers")
base_path = dbutils.widgets.get("base_path").rstrip("/")
catalog_name = dbutils.widgets.get("catalog_name")
secret_scope = dbutils.widgets.get("secret_scope")
secret_key = dbutils.widgets.get("secret_key")
trigger_mode = dbutils.widgets.get("trigger_mode")
max_runtime_minutes = int(dbutils.widgets.get("max_runtime_minutes"))
max_offsets_per_trigger = int(dbutils.widgets.get("max_offsets_per_trigger"))
checkpoint_namespace = dbutils.widgets.get("checkpoint_namespace")
fail_after_committed_batch = (
    dbutils.widgets.get("fail_after_committed_batch").lower() == "true"
)
starting_offsets = dbutils.widgets.get("starting_offsets")
stream_run_id = dbutils.widgets.get("stream_run_id")

if not re.fullmatch(r"[A-Za-z0-9_]+", catalog_name):
    raise ValueError("catalog_name contains unsupported characters")
if not re.fullmatch(r"[A-Za-z0-9_.@-]+", secret_scope):
    raise ValueError("secret_scope contains unsupported characters")
if not re.fullmatch(r"[A-Za-z0-9_.@-]+", secret_key):
    raise ValueError("secret_key contains unsupported characters")
if not re.fullmatch(r"[a-z0-9_-]{3,80}", checkpoint_namespace):
    raise ValueError("checkpoint_namespace contains unsupported characters")
if not re.fullmatch(r"[a-z0-9-]{8,64}", stream_run_id):
    raise ValueError("stream_run_id contains unsupported characters")
if not bootstrap.endswith(".servicebus.windows.net:9093"):
    raise ValueError("kafka_bootstrap_servers must be an Event Hubs Kafka endpoint")
if not base_path.startswith("abfss://retailpulse@"):
    raise ValueError("base_path must be the RetailPulse ADLS filesystem")
if not 1 <= max_runtime_minutes <= 30:
    raise ValueError("max_runtime_minutes must be between 1 and 30")
if not 1 <= max_offsets_per_trigger <= 25000:
    raise ValueError("max_offsets_per_trigger must be between 1 and 25000")
if trigger_mode != "available_now":
    raise ValueError("serverless Stage 7 supports only the available_now trigger")

connection_string = dbutils.secrets.get(scope=secret_scope, key=secret_key)
if not connection_string.startswith("Endpoint=sb://"):
    raise ValueError("the Event Hubs secret is not a namespace connection string")
escaped_connection_string = connection_string.replace("\\", "\\\\").replace('"', '\\"')
sasl_jaas = (
    'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required '
    f'username="$ConnectionString" password="{escaped_connection_string}";'
)

bronze_schema = "retailpulse_bronze"
silver_schema = "retailpulse_silver"
ops_schema = "retailpulse_ops"
for schema_name in (bronze_schema, silver_schema, ops_schema):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog_name}`.`{schema_name}`")

bronze_table = f"`{catalog_name}`.`{bronze_schema}`.`streaming_events`"
silver_table = f"`{catalog_name}`.`{silver_schema}`.`streaming_events`"
quarantine_table = f"`{catalog_name}`.`{ops_schema}`.`streaming_quarantine`"
audit_table = f"`{catalog_name}`.`{ops_schema}`.`streaming_batch_runs`"
bronze_path = f"{base_path}/bronze/streaming/events"
silver_path = f"{base_path}/silver/streaming/events"
quarantine_path = f"{base_path}/quarantine/streaming/events"
audit_path = f"{base_path}/bronze/_audit/streaming_batch_runs"
checkpoint_path = f"{base_path}/checkpoints/stage07/{checkpoint_namespace}/events"

event_schema = StructType(
    [
        StructField("event_id", StringType()),
        StructField("event_type", StringType()),
        StructField("customer_id", StringType()),
        StructField("product_id", StringType()),
        StructField("order_id", StringType()),
        StructField("quantity", IntegerType()),
        StructField("price", DecimalType(12, 2)),
        StructField("country", StringType()),
        StructField("query", StringType()),
        StructField("event_timestamp", TimestampType()),
        StructField("schema_version", IntegerType()),
    ]
)


def ensure_external_table(frame: DataFrame, table_name: str, path: str) -> None:
    if not spark.catalog.tableExists(table_name.replace("`", "")):
        frame.limit(0).write.format("delta").mode("ignore").save(path)
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table_name} USING DELTA LOCATION '{path}'")


def merge_frame(
    frame: DataFrame,
    table_name: str,
    path: str,
    condition: str,
    *,
    update_matched: bool = False,
) -> dict[str, int | str]:
    ensure_external_table(frame, table_name, path)
    view_name = (
        "stage07_"
        + table_name.replace("`", "").split(".")[-1]
        + "_"
        + checkpoint_namespace.replace("-", "_")
    )
    frame.createOrReplaceTempView(view_name)
    matched_clause = "WHEN MATCHED THEN UPDATE SET * " if update_matched else ""
    spark.sql(
        f"MERGE INTO {table_name} AS target USING {view_name} AS source ON {condition} "
        f"{matched_clause}WHEN NOT MATCHED THEN INSERT *"
    )
    history = spark.sql(f"DESCRIBE HISTORY {table_name} LIMIT 1").select(
        "version", "operation", "operationMetrics"
    ).first()
    return {
        "version": int(history["version"]),
        "operation": history["operation"],
        **{
            key: int(value) if str(value).isdigit() else value
            for key, value in dict(history["operationMetrics"] or {}).items()
        },
    }


def process_batch(batch_df: DataFrame, batch_id: int) -> None:
    started_at = time.monotonic()
    input_rows = batch_df.count()
    if input_rows == 0:
        return

    bronze = batch_df.select(
        F.col("topic").alias("source_topic"),
        "partition",
        "offset",
        "kafka_timestamp",
        "ingestion_timestamp",
        "raw_payload",
        "scenario",
        "stream_run_id",
        F.lit(checkpoint_namespace).alias("checkpoint_namespace"),
    )
    bronze_history = merge_frame(
        bronze,
        bronze_table,
        bronze_path,
        "target.stream_run_id = source.stream_run_id AND "
        "target.source_topic = source.source_topic AND "
        "target.partition = source.partition AND target.offset = source.offset",
    )

    parsed = bronze.withColumn("event", F.from_json("raw_payload", event_schema)).select(
        "source_topic",
        "partition",
        "offset",
        "kafka_timestamp",
        "ingestion_timestamp",
        "raw_payload",
        "scenario",
        "stream_run_id",
        "checkpoint_namespace",
        "event.*",
    )
    schema_valid = (
        F.col("event_id").isNotNull()
        & F.col("event_type").isin(
            "product_view",
            "search",
            "add_to_cart",
            "checkout",
            "purchase",
            "payment",
            "inventory_update",
        )
        & F.col("event_timestamp").isNotNull()
        & (F.col("schema_version") == 1)
    )
    product_valid = ~F.col("event_type").isin(
        "product_view", "add_to_cart", "purchase", "inventory_update"
    ) | F.col("product_id").isNotNull()
    quantity_valid = ~F.col("event_type").isin("purchase", "inventory_update") | (
        F.col("quantity").isNotNull() & (F.col("quantity") > 0)
    )
    price_valid = F.col("price").isNull() | (F.col("price") >= 0)
    is_valid = F.coalesce(
        schema_valid & product_valid & quantity_valid & price_valid,
        F.lit(False),
    )
    is_late = is_valid & (
        F.col("event_timestamp") < F.current_timestamp() - F.expr("INTERVAL 30 MINUTES")
    )
    accepted = parsed.filter(is_valid & ~is_late)
    rejected = parsed.filter(~is_valid | is_late).select(
        "event_id",
        "raw_payload",
        "source_topic",
        "partition",
        "offset",
        "kafka_timestamp",
        "ingestion_timestamp",
        "scenario",
        "stream_run_id",
        "checkpoint_namespace",
        F.when(is_late, F.lit("LATE_EVENT"))
        .otherwise(F.lit("SCHEMA_OR_BUSINESS_RULE"))
        .alias("error_type"),
        F.when(is_late, F.lit("event_timestamp is older than the 30-minute watermark"))
        .otherwise(F.lit("payload does not satisfy the version 1 event contract"))
        .alias("error_message"),
    )
    quarantine_history = merge_frame(
        rejected,
        quarantine_table,
        quarantine_path,
        "target.stream_run_id = source.stream_run_id AND "
        "target.source_topic = source.source_topic AND "
        "target.partition = source.partition AND target.offset = source.offset",
    )

    silver_source = accepted.dropDuplicates(["event_id"]).select(
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
        "source_topic",
        "partition",
        "offset",
        "kafka_timestamp",
        "ingestion_timestamp",
        "scenario",
        "stream_run_id",
        "checkpoint_namespace",
    )
    silver_history = merge_frame(
        silver_source,
        silver_table,
        silver_path,
        "target.event_id = source.event_id",
    )

    duplicate_rows = accepted.count() - silver_source.count()
    latency = accepted.select(
        (
            F.unix_millis("ingestion_timestamp") - F.unix_millis("event_timestamp")
        ).alias("latency_ms")
    ).agg(
        F.avg("latency_ms").alias("average_latency_ms"),
        F.max("latency_ms").alias("maximum_latency_ms"),
    ).first()
    duration_seconds = round(time.monotonic() - started_at, 3)
    audit = spark.createDataFrame(
        [
            (
                checkpoint_namespace,
                batch_id,
                input_rows,
                int(silver_history.get("numTargetRowsInserted", 0)),
                rejected.count(),
                duplicate_rows,
                duration_seconds,
                float(latency["average_latency_ms"] or 0),
                int(latency["maximum_latency_ms"] or 0),
                json.dumps(bronze_history, sort_keys=True),
                json.dumps(silver_history, sort_keys=True),
                json.dumps(quarantine_history, sort_keys=True),
            )
        ],
        "checkpoint_namespace STRING, batch_id LONG, records_read LONG, records_written LONG, "
        "records_rejected LONG, records_duplicate LONG, duration_seconds DOUBLE, "
        "average_latency_ms DOUBLE, maximum_latency_ms LONG, bronze_metrics_json STRING, "
        "silver_metrics_json STRING, quarantine_metrics_json STRING",
    ).withColumn("completed_at", F.current_timestamp())
    merge_frame(
        audit,
        audit_table,
        audit_path,
        "target.checkpoint_namespace = source.checkpoint_namespace AND "
        "target.batch_id = source.batch_id",
        update_matched=True,
    )
    if fail_after_committed_batch:
        raise RuntimeError("STAGE7_INTENTIONAL_FAILURE_AFTER_COMMITTED_BATCH")


raw = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", bootstrap)
    .option("subscribe", "customer-events,order-events,inventory-events")
    .option("startingOffsets", starting_offsets)
    .option("maxOffsetsPerTrigger", max_offsets_per_trigger)
    .option("failOnDataLoss", "true")
    .option("includeHeaders", "true")
    .option("kafka.security.protocol", "SASL_SSL")
    .option("kafka.sasl.mechanism", "PLAIN")
    .option("kafka.sasl.jaas.config", sasl_jaas)
    .option("kafka.request.timeout.ms", "60000")
    .option("kafka.session.timeout.ms", "30000")
    .load()
    .selectExpr(
        "CAST(value AS STRING) AS raw_payload",
        "topic",
        "partition",
        "offset",
        "timestamp AS kafka_timestamp",
        "current_timestamp() AS ingestion_timestamp",
        "CAST(element_at(filter(headers, x -> x.key = 'retailpulse_scenario'), 1).value "
        "AS STRING) AS scenario",
        "CAST(element_at(filter(headers, x -> x.key = 'retailpulse_run_id'), 1).value "
        "AS STRING) AS stream_run_id",
    )
    .filter(F.col("stream_run_id") == F.lit(stream_run_id))
    .withColumn(
        "watermark_event_timestamp",
        F.from_json("raw_payload", event_schema).getField("event_timestamp"),
    )
    .withWatermark("watermark_event_timestamp", "30 minutes")
)

writer = raw.writeStream.foreachBatch(process_batch).option(
    "checkpointLocation", checkpoint_path
)
writer = writer.trigger(availableNow=True)
query = writer.queryName(f"retailpulse_stage07_{checkpoint_namespace}").start()
query.awaitTermination(max_runtime_minutes * 60)
if query.isActive:
    query.stop()
    query.awaitTermination()
    raise TimeoutError("Stage 7 stream exceeded max_runtime_minutes")

def counts_by_scenario(table_name: str) -> dict[str, int]:
    return {
        str(row["scenario"] or "unknown"): int(row["count"])
        for row in spark.table(table_name)
        .filter(F.col("stream_run_id") == stream_run_id)
        .groupBy("scenario")
        .count()
        .collect()
    }


def run_count(table_name: str) -> int:
    return spark.table(table_name).filter(F.col("stream_run_id") == stream_run_id).count()


last_progress = query.lastProgress or {}
audit_results = [
    {
        "batch_id": int(row["batch_id"]),
        "records_read": int(row["records_read"]),
        "records_written": int(row["records_written"]),
        "records_rejected": int(row["records_rejected"]),
        "records_duplicate": int(row["records_duplicate"]),
        "duration_seconds": float(row["duration_seconds"]),
        "average_latency_ms": float(row["average_latency_ms"]),
        "maximum_latency_ms": int(row["maximum_latency_ms"]),
        "bronze_history": json.loads(row["bronze_metrics_json"]),
        "silver_history": json.loads(row["silver_metrics_json"]),
        "quarantine_history": json.loads(row["quarantine_metrics_json"]),
    }
    for row in spark.table(audit_table)
    .filter(F.col("checkpoint_namespace") == checkpoint_namespace)
    .orderBy("batch_id")
    .collect()
]


summary = {
    "status": "STAGE7_STREAM_OK",
    "checkpoint_namespace": checkpoint_namespace,
    "stream_run_id": stream_run_id,
    "checkpoint_path": checkpoint_path,
    "trigger_mode": trigger_mode,
    "audit_results": audit_results,
    "bronze_total": run_count(bronze_table),
    "silver_total": run_count(silver_table),
    "silver_unique_event_ids": spark.table(silver_table)
    .filter(F.col("stream_run_id") == stream_run_id)
    .select("event_id")
    .distinct()
    .count(),
    "quarantine_total": run_count(quarantine_table),
    "audit_total": spark.table(audit_table).count(),
    "stream_progress": {
        "batch_id": last_progress.get("batchId"),
        "num_input_rows": last_progress.get("numInputRows", 0),
        "input_rows_per_second": last_progress.get("inputRowsPerSecond", 0),
        "processed_rows_per_second": last_progress.get("processedRowsPerSecond", 0),
        "duration_ms": last_progress.get("durationMs", {}),
        "event_time": last_progress.get("eventTime", {}),
    },
    "scenario_counts": {
        "bronze": counts_by_scenario(bronze_table),
        "silver": counts_by_scenario(silver_table),
        "quarantine": counts_by_scenario(quarantine_table),
    },
    "tables": {
        "bronze": bronze_table.replace("`", ""),
        "silver": silver_table.replace("`", ""),
        "quarantine": quarantine_table.replace("`", ""),
        "audit": audit_table.replace("`", ""),
    },
}
dbutils.notebook.exit(json.dumps(summary, sort_keys=True))
