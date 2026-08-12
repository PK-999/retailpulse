# Databricks notebook source
from delta.tables import DeltaTable
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


def merge_insert_only(source_df, target_path: str, condition: str, partition_by: str | None = None):
    """Insert unseen records without collecting source data on the driver."""
    if DeltaTable.isDeltaTable(spark, target_path):
        (
            DeltaTable.forPath(spark, target_path)
            .alias("target")
            .merge(source_df.alias("source"), condition)
            .whenNotMatchedInsertAll()
            .execute()
        )
        return
    writer = source_df.write.format("delta").mode("overwrite")
    if partition_by:
        writer = writer.partitionBy(partition_by)
    writer.save(target_path)


def merge_current(source_df, target_path: str, condition: str):
    """Upsert the latest version of a bounded entity/business-key dataset."""
    if DeltaTable.isDeltaTable(spark, target_path):
        (
            DeltaTable.forPath(spark, target_path)
            .alias("target")
            .merge(source_df.alias("source"), condition)
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        source_df.write.format("delta").mode("overwrite").save(target_path)

for name, schema in datasets.items():
    source = f"{landing_path}/{name}.jsonl"
    bronze = f"{base_path}/bronze/{name}"
    silver = f"{base_path}/silver/{name}"
    raw = (
        spark.read.schema(schema)
        .json(source)
        .withColumn("source_file", F.input_file_name())
        .withColumn("ingestion_timestamp", F.current_timestamp())
        .withColumn("ingestion_date", F.current_date())
        .withColumn("pipeline_run_id", F.lit(run_id))
        .withColumn(
            "_record_hash",
            F.sha2(F.to_json(F.struct(*[F.col(field.name) for field in schema.fields])), 256),
        )
    )
    merge_insert_only(
        raw,
        bronze,
        " AND ".join(
            [
                "target.ingestion_date = source.ingestion_date",
                "target.pipeline_run_id = source.pipeline_run_id",
                "target._record_hash = source._record_hash",
            ]
        ),
        partition_by="ingestion_date",
    )

    key = {"customers": "customer_id", "products": "product_id", "orders": "order_id"}.get(name)
    clean = raw.dropDuplicates([key] if key else ["order_id", "product_id"])
    if name == "orders":
        clean = clean.withColumn("order_timestamp", F.to_timestamp("order_timestamp"))
    if name == "order_items":
        valid = (F.col("quantity") > 0) & (F.col("unit_price") >= 0)
        merge_insert_only(
            clean.filter(~valid),
            f"{base_path}/quarantine/{name}",
            " AND ".join(
                [
                    "target.pipeline_run_id = source.pipeline_run_id",
                    "target._record_hash = source._record_hash",
                ]
            ),
        )
        clean = clean.filter(valid)

    if key:
        merge_current(clean, silver, f"target.{key} = source.{key}")
    else:
        merge_insert_only(clean, silver, "target._record_hash = source._record_hash")
