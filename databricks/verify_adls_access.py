# Databricks notebook source
from datetime import UTC, datetime

from pyspark.sql import functions as F

dbutils.widgets.text(
    "base_path", "abfss://retailpulse@STORAGE_ACCOUNT_NAME.dfs.core.windows.net"
)
dbutils.widgets.text("verification_id", "stage-04-manual")
base_path = dbutils.widgets.get("base_path").rstrip("/")
verification_id = dbutils.widgets.get("verification_id")

if "STORAGE_ACCOUNT_NAME" in base_path:
    raise ValueError("Replace the base_path placeholder before running the verification")
if not verification_id.replace("-", "").replace("_", "").isalnum():
    raise ValueError("verification_id contains unsupported characters")

target_path = f"{base_path}/silver/_access_tests/{verification_id}"
expected = spark.createDataFrame(
    [(verification_id, datetime.now(UTC))],
    "verification_id string, verified_at timestamp",
)
expected.write.format("delta").mode("overwrite").save(target_path)

actual = spark.read.format("delta").load(target_path)
if actual.filter(F.col("verification_id") == verification_id).count() != 1:
    raise AssertionError("ADLS Delta write/read verification did not reconcile")

print(f"STAGE4_ADLS_ACCESS_OK verification_id={verification_id} path={target_path}")
