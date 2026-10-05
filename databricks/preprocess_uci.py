# Databricks notebook source
import hashlib
import io
import json
import zipfile

import pandas as pd

dbutils.widgets.text("raw_path", "")
dbutils.widgets.text("normalized_root", "")
dbutils.widgets.text("adf_pipeline_run_id", "")
dbutils.widgets.text("expected_sha256", "")
dbutils.widgets.text("expected_size_bytes", "")

raw_path = dbutils.widgets.get("raw_path").rstrip("/")
normalized_root = dbutils.widgets.get("normalized_root").rstrip("/")
adf_pipeline_run_id = dbutils.widgets.get("adf_pipeline_run_id")
expected_sha256 = dbutils.widgets.get("expected_sha256").lower()
expected_size_bytes = int(dbutils.widgets.get("expected_size_bytes"))

if not raw_path.endswith(".zip"):
    raise ValueError("raw_path must identify the immutable UCI ZIP archive")
if not normalized_root or not adf_pipeline_run_id:
    raise ValueError("normalized_root and adf_pipeline_run_id are required")
if adf_pipeline_run_id not in raw_path or adf_pipeline_run_id not in normalized_root:
    raise ValueError("raw and normalized paths must be scoped by the ADF pipeline run ID")

dataset_names = ("customers", "products", "orders", "order_items")
dataset_paths = {name: f"{normalized_root}/{name}.jsonl" for name in dataset_names}
manifest_path = f"{normalized_root}/_manifest.jsonl"

normalized_parent, delivery_directory = normalized_root.rsplit("/", 1)
dbutils.fs.mkdirs(normalized_parent)
parent_entries = {entry.name.rstrip("/") for entry in dbutils.fs.ls(normalized_parent)}
delivery_exists = delivery_directory in parent_entries
delivery_entries = (
    {entry.name.rstrip("/") for entry in dbutils.fs.ls(normalized_root)}
    if delivery_exists
    else set()
)
existing_paths = {name: f"{name}.jsonl" in delivery_entries for name in dataset_names}
manifest_exists = "_manifest.jsonl" in delivery_entries
if delivery_exists:
    if not all(existing_paths.values()) or not manifest_exists:
        raise RuntimeError("partial normalized delivery exists; refusing to overwrite it")
    counts = {name: spark.read.json(path).count() for name, path in dataset_paths.items()}
    result = {
        "status": "SUCCEEDED",
        "idempotent_reuse": True,
        "adf_pipeline_run_id": adf_pipeline_run_id,
        "raw_path": raw_path,
        "normalized_root": normalized_root,
        "counts": counts,
    }
    dbutils.notebook.exit(json.dumps(result, sort_keys=True))

archive_row = spark.read.format("binaryFile").load(raw_path).select("content", "length").first()
if archive_row is None:
    raise RuntimeError("ADF archive was not found at the expected immutable path")

archive_bytes = bytes(archive_row["content"])
archive_size = int(archive_row["length"])
archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
if archive_size != expected_size_bytes:
    raise ValueError(
        f"archive size mismatch: expected {expected_size_bytes}, received {archive_size}"
    )
if archive_sha256 != expected_sha256:
    raise ValueError(
        f"archive SHA-256 mismatch: expected {expected_sha256}, received {archive_sha256}"
    )

with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
    members = [name for name in archive.namelist() if not name.endswith("/")]
    if members != ["Online Retail.xlsx"]:
        raise ValueError(f"unexpected UCI ZIP members: {members}")
    workbook_bytes = archive.read(members[0])

source = pd.read_excel(io.BytesIO(workbook_bytes), sheet_name=0, engine="openpyxl")
expected_columns = {
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
}
if set(source.columns) != expected_columns:
    raise ValueError(f"unexpected workbook columns: {sorted(source.columns)}")


def clean_identifier(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


invoice = source["InvoiceNo"].map(clean_identifier)
stock = source["StockCode"].map(clean_identifier)
customer = source["CustomerID"].map(clean_identifier)
description = source["Description"].fillna("").astype(str).str.strip()
country = source["Country"].fillna("").astype(str).str.strip()
quantity = pd.to_numeric(source["Quantity"], errors="coerce").fillna(0).astype("int64")
unit_price = pd.to_numeric(source["UnitPrice"], errors="coerce").fillna(0.0).astype("float64")
order_timestamp = pd.to_datetime(source["InvoiceDate"], errors="coerce").dt.strftime(
    "%Y-%m-%d %H:%M:%S"
)

valid_key = invoice.ne("") & stock.ne("")
normalized = pd.DataFrame(
    {
        "order_id": invoice[valid_key],
        "product_id": stock[valid_key],
        "description": description[valid_key],
        "quantity": quantity[valid_key],
        "order_timestamp": order_timestamp[valid_key].fillna(""),
        "unit_price": unit_price[valid_key],
        "customer_id": customer[valid_key],
        "country": country[valid_key],
    }
)

frames = {
    "customers": (
        normalized.loc[normalized["customer_id"].ne(""), ["customer_id", "country"]]
        .drop_duplicates("customer_id", keep="last")
        .reset_index(drop=True)
    ),
    "products": (
        normalized[["product_id", "description", "unit_price"]]
        .drop_duplicates("product_id", keep="last")
        .reset_index(drop=True)
    ),
    "orders": (
        normalized[["order_id", "customer_id", "order_timestamp", "country"]]
        .assign(
            is_cancelled=normalized["order_id"]
            .str.startswith("C")
            .map({True: "true", False: "false"})
        )
        .drop_duplicates("order_id", keep="last")
        .reset_index(drop=True)
    ),
    "order_items": normalized[["order_id", "product_id", "quantity", "unit_price"]].reset_index(
        drop=True
    ),
}

counts = {}
for name, frame in frames.items():
    counts[name] = int(len(frame.index))
    spark.createDataFrame(frame).write.mode("error").json(dataset_paths[name])

manifest = {
    "status": "SUCCEEDED",
    "idempotent_reuse": False,
    "adf_pipeline_run_id": adf_pipeline_run_id,
    "source_archive": raw_path,
    "source_archive_bytes": archive_size,
    "source_archive_sha256": archive_sha256,
    "normalized_root": normalized_root,
    "counts": counts,
}
spark.createDataFrame([(json.dumps(manifest, sort_keys=True),)], ["value"]).coalesce(1).write.mode(
    "error"
).text(manifest_path)

dbutils.notebook.exit(json.dumps(manifest, sort_keys=True))
