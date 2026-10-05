# Databricks notebook source
import json
import re

from pyspark.sql import functions as F

dbutils.widgets.text("catalog_name", "")
dbutils.widgets.text("stream_run_id", "")
dbutils.widgets.text("checkpoint_namespace", "")

catalog_name = dbutils.widgets.get("catalog_name")
stream_run_id = dbutils.widgets.get("stream_run_id")
checkpoint_namespace = dbutils.widgets.get("checkpoint_namespace")
if not re.fullmatch(r"[A-Za-z0-9_]+", catalog_name):
    raise ValueError("catalog_name contains unsupported characters")
if not re.fullmatch(r"[a-f0-9-]{36}", stream_run_id):
    raise ValueError("stream_run_id must be a UUID")
if checkpoint_namespace != f"stage07-{stream_run_id}":
    raise ValueError("checkpoint_namespace does not match stream_run_id")

bronze_table = f"`{catalog_name}`.`retailpulse_bronze`.`streaming_events`"
silver_table = f"`{catalog_name}`.`retailpulse_silver`.`streaming_events`"
quarantine_table = f"`{catalog_name}`.`retailpulse_ops`.`streaming_quarantine`"
audit_table = f"`{catalog_name}`.`retailpulse_ops`.`streaming_batch_runs`"


def run_frame(table_name: str):
    return spark.table(table_name).filter(F.col("stream_run_id") == stream_run_id)


def scenario_counts(table_name: str) -> dict[str, int]:
    return {
        str(row["scenario"]): int(row["count"])
        for row in run_frame(table_name).groupBy("scenario").count().collect()
    }


audit_rows = (
    spark.table(audit_table)
    .filter(F.col("checkpoint_namespace") == checkpoint_namespace)
    .orderBy("batch_id")
    .collect()
)
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
    for row in audit_rows
]
recovery = next(result for result in audit_results if result["batch_id"] == 1)
bronze = run_frame(bronze_table)
transport_metadata_nulls = bronze.filter(
    F.col("source_topic").isNull()
    | F.col("partition").isNull()
    | F.col("offset").isNull()
    | F.col("kafka_timestamp").isNull()
    | F.col("ingestion_timestamp").isNull()
).count()
summary = {
    "status": "STAGE7_DURABLE_EVIDENCE_VERIFIED",
    "stream_run_id": stream_run_id,
    "checkpoint_namespace": checkpoint_namespace,
    "bronze_total": run_frame(bronze_table).count(),
    "silver_total": run_frame(silver_table).count(),
    "silver_unique_event_ids": run_frame(silver_table).select("event_id").distinct().count(),
    "quarantine_total": run_frame(quarantine_table).count(),
    "transport_metadata_nulls": transport_metadata_nulls,
    "scenario_counts": {
        "bronze": scenario_counts(bronze_table),
        "silver": scenario_counts(silver_table),
        "quarantine": scenario_counts(quarantine_table),
    },
    "audit_results": audit_results,
}

assert summary["bronze_total"] == 460
assert summary["silver_total"] == 411
assert summary["silver_unique_event_ids"] == 411
assert summary["quarantine_total"] == 30
assert summary["transport_metadata_nulls"] == 0
assert len(audit_results) == 2
assert recovery["records_read"] == 40
assert int(recovery["bronze_history"].get("numTargetRowsInserted", -1)) == 0
assert int(recovery["silver_history"].get("numTargetRowsInserted", -1)) == 0
assert summary["scenario_counts"] == {
    "bronze": {
        "normal": 60,
        "duplicate": 60,
        "late-data": 60,
        "malformed": 40,
        "traffic-spike": 200,
        "checkpoint-recovery": 40,
    },
    "silver": {
        "normal": 60,
        "duplicate": 41,
        "late-data": 40,
        "malformed": 30,
        "traffic-spike": 200,
        "checkpoint-recovery": 40,
    },
    "quarantine": {"late-data": 20, "malformed": 10},
}
dbutils.notebook.exit(json.dumps(summary, sort_keys=True))
