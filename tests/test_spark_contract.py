"""Contract parity and real Spark/Delta replay fixtures.

Run Spark tests in the cached runner image; the normal Python suite exercises the
same serialized validator and notebook bundler without requiring Java.
"""

import ast
import base64
import json
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from retailpulse.contracts import RetailEvent

ROOT = Path(__file__).parents[1]
BASE = {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "event_type": "purchase",
    "product_id": "P1",
    "order_id": "O1",
    "quantity": 2,
    "price": "1.005",
    "event_timestamp": "2026-10-04T12:00:00+05:30",
    "schema_version": 1,
}


def validator(**options):
    from retailpulse.spark_contract import make_event_validator, read_contract_source

    return make_event_validator(read_contract_source(), **options)


def test_validator_preserves_decimal_and_normalizes_uuid_and_timezone() -> None:
    result = validator()(json.dumps(BASE), "order-events")
    assert result["error_type"] is None
    assert result["event_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert result["price"] == "1.005"
    assert result["event_timestamp"] == datetime(2026, 10, 4, 6, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": "not-a-uuid"},
        {"event_type": "unknown"},
        {"schema_version": True},
        {"schema_version": "1"},
        {"event_timestamp": "2026-10-04T12:00:00"},
        {"event_timestamp": 0},
        {"event_timestamp": "0"},
        {"extra": "forbidden"},
        {"product_id": ""},
        {"product_id": "  "},
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": 1.5},
        {"quantity": True},
        {"quantity": "2"},
        {"quantity": 2147483648},
        {"price": "NaN"},
        {"price": "Infinity"},
        {"price": "-0.01"},
        {"order_id": ""},
        {"order_id": "  "},
    ],
)
def test_structured_invalid_payloads_follow_python_contract(changes) -> None:
    raw = json.dumps({**BASE, **changes})
    with pytest.raises(ValidationError):
        RetailEvent.model_validate_json(raw)
    result = validator()(raw, "order-events")
    assert result["error_type"] == "SCHEMA_VALIDATION"
    assert result["error_message"]


@pytest.mark.parametrize("field", ["schema_version", "order_id", "price", "product_id"])
def test_missing_purchase_fields_are_rejected(field) -> None:
    payload = dict(BASE)
    del payload[field]
    result = validator()(json.dumps(payload), "order-events")
    assert result["error_type"] == "SCHEMA_VALIDATION"
    assert result["error_message"]


@pytest.mark.parametrize("raw", ["{broken", "[]", "null", '"text"'])
def test_invalid_json_shapes_are_quarantined(raw) -> None:
    result = validator()(raw, "order-events")
    assert result["error_type"] == "SCHEMA_VALIDATION"
    assert result["error_message"]


def test_topic_mismatch_has_specific_reason() -> None:
    result = validator()(json.dumps(BASE), "customer-events")
    assert result["error_type"] == "TOPIC_MISMATCH"
    assert "order-events" in result["error_message"]


@pytest.mark.parametrize(
    "event_type,topic,fields",
    [
        ("product_view", "customer-events", {"product_id": "P1"}),
        ("search", "customer-events", {"query": "shoes"}),
        ("add_to_cart", "customer-events", {"product_id": "P1"}),
        ("checkout", "order-events", {}),
        (
            "purchase",
            "order-events",
            {"product_id": "P1", "order_id": "O1", "quantity": 1, "price": "0.145"},
        ),
        ("payment", "order-events", {}),
        ("inventory_update", "inventory-events", {"product_id": "P1", "quantity": 1}),
    ],
)
def test_every_event_type_matches_python_validation(event_type, topic, fields) -> None:
    payload = {
        "event_id": str(UUID(int=10)),
        "event_type": event_type,
        "event_timestamp": "2026-10-04T06:30:00Z",
        "schema_version": 1,
        **fields,
    }
    event = RetailEvent.model_validate_json(json.dumps(payload))
    result = validator()(json.dumps(payload), topic)
    assert result["error_type"] is None
    assert result["event_type"] == event.event_type
    assert result["quantity"] == event.quantity
    assert result["price"] == (str(event.price) if event.price is not None else None)


@pytest.mark.parametrize("price", ["1.005", "10000000000.00"])
def test_legacy_decimal_storage_quarantines_values_instead_of_rounding(price) -> None:
    raw = json.dumps({**BASE, "price": price})
    assert RetailEvent.model_validate_json(raw).price == Decimal(price)
    result = validator(decimal_precision=12, decimal_scale=2)(raw, "order-events")
    assert result["error_type"] == "SILVER_REPRESENTATION"
    assert "DECIMAL(12,2)" in result["error_message"]
    assert validator()(raw, "order-events")["price"] == price


def test_legacy_decimal_accepts_exactly_representable_values() -> None:
    result = validator(decimal_precision=12, decimal_scale=2)(
        json.dumps({**BASE, "price": "1.200"}), "order-events"
    )
    assert result["error_type"] is None
    assert result["price"] == "1.200"


def test_bundled_notebook_is_standalone_and_contains_current_contract() -> None:
    from retailpulse.spark_contract import bundle_notebook

    notebook = bundle_notebook(ROOT / "databricks" / "stream_bronze_silver.py")
    compile(notebook, "bundled_notebook.py", "exec")
    # Evaluate only the bundled helper prelude; no credentials, widgets, or cloud calls.
    prelude = notebook.split("# RETAILPULSE_SHARED_CONTRACT_END", 1)[0]
    namespace = {"__name__": "__main__"}
    exec(compile(prelude, "bundled_notebook.py", "exec"), namespace)
    result = namespace["make_event_validator"](namespace["RETAILPULSE_CONTRACT_SOURCE"])(
        json.dumps(BASE), "order-events"
    )
    assert result["error_type"] is None
    assert result["price"] == "1.005"


def test_validator_runs_in_worker_without_project_package() -> None:
    pytest.importorskip("pyspark")
    from pyspark import cloudpickle

    validate = validator()
    # Even if this driver already constructed the model, its cache must not leak
    # into the closure or require an import of a driver-only synthetic module.
    assert validate(json.dumps(BASE), "order-events")["error_type"] is None
    encoded = base64.b64encode(cloudpickle.dumps(validate)).decode("ascii")
    worker = """
import base64, importlib.abc, json, sys
from pyspark import cloudpickle
class NoProjectImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("retailpulse"):
            raise ImportError("project package is unavailable on this worker")
sys.meta_path.insert(0, NoProjectImports())
validate = cloudpickle.loads(base64.b64decode(sys.argv[1]))
print(json.dumps(validate(sys.argv[2], "order-events"), default=str))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", worker, encoded, json.dumps(BASE)],
        text=True,
        capture_output=True,
        check=True,
    )
    parsed = json.loads(result.stdout)
    assert parsed["error_type"] is None
    assert parsed["price"] == "1.005"


@pytest.fixture(scope="module")
def spark():
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession

    # Resolve only the already-cached local jars: this test needs no Maven/network.
    jars = list(Path("/root/.ivy2.5.2/jars").glob("*delta*.jar"))
    if not jars:
        pytest.fail("cached Delta jars required; build tools/Dockerfile.spark before Spark tests")
    session = (
        SparkSession.builder.master("local[2]")
        .appName("RetailPulseContractFixtures")
        .config("spark.jars", ",".join(str(path) for path in jars))
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog"
        )
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.databricks.delta.snapshotPartitions", "2")
        .config("spark.sql.warehouse.dir", "/tmp/retailpulse-contract-warehouse")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.executorEnv.TZ", "Asia/Kolkata")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def raw_frame(spark, items):
    received = datetime(2026, 10, 4, 7, 0, tzinfo=UTC)
    rows = [
        (raw, topic, 0, offset, received, received) for offset, (raw, topic) in enumerate(items)
    ]
    return spark.createDataFrame(
        rows,
        "raw_payload STRING, topic STRING, partition INT, offset LONG, "
        "kafka_timestamp TIMESTAMP, ingestion_timestamp TIMESTAMP",
    )


def test_executor_timezone_does_not_shift_event_instants_or_lateness(spark):
    from pyspark.sql import functions as F
    from pyspark.sql.types import StringType

    from retailpulse.spark_contract import classify_events, read_contract_source

    def worker_timezone():
        import os

        return os.environ.get("TZ")

    worker_tz = F.udf(worker_timezone, StringType())
    assert spark.range(1).select(worker_tz()).first()[0] == "Asia/Kolkata"
    classified = classify_events(
        raw_frame(spark, [(json.dumps(BASE), "order-events")]), read_contract_source()
    )
    row = classified.select("error_type", F.unix_timestamp("event_timestamp")).first()
    assert row[0] is None
    assert row[1] == int(datetime(2026, 10, 4, 6, 30, tzinfo=UTC).timestamp())


def test_real_spark_rejects_structured_bad_events_and_retains_raw_late_metadata(spark) -> None:
    from retailpulse.spark_contract import classify_events, read_contract_source

    invalid = [
        {"event_id": "bad-uuid"},
        {"event_type": "unknown"},
        {"schema_version": 2},
        {"event_timestamp": "2026-10-04T06:30:00"},
        {"unexpected": 1},
        {"product_id": ""},
        {"quantity": 0},
        {"quantity": 1.5},
        {"price": "NaN"},
        {"price": "-1"},
        {"order_id": ""},
        {"price": None},
    ]
    items = [(json.dumps(BASE), "order-events")]
    items.extend((json.dumps({**BASE, **patch}), "order-events") for patch in invalid)
    items.append((json.dumps(BASE), "customer-events"))
    late = json.dumps({**BASE, "event_timestamp": "2020-01-01T00:00:00Z"})
    items.append((late, "order-events"))
    items.append(("{broken", "order-events"))
    classified = classify_events(raw_frame(spark, items), read_contract_source())
    rows = classified.collect()
    accepted = [row for row in rows if row.error_type is None]
    rejected = [row for row in rows if row.error_type is not None]
    assert len(accepted) == 1
    assert accepted[0].price == "1.005"
    assert len(rejected) == 15
    assert {row.raw_payload for row in rows} == {raw for raw, _ in items}
    assert all(row.error_message and row.topic and row.partition == 0 for row in rejected)
    assert {row.offset for row in rows} == set(range(16))
    late_row = next(row for row in rows if row.raw_payload == late)
    assert late_row.error_type == "LATE_EVENT"


def test_real_cloud_checkpoint_replay_after_committed_merges(spark, tmp_path) -> None:
    from pyspark.sql import DataFrame
    from pyspark.sql import functions as F
    from pyspark.sql.utils import StreamingQueryException

    from retailpulse.spark_contract import bundle_notebook

    raw = json.dumps(BASE)
    bad = json.dumps({**BASE, "event_id": "bad-uuid"})
    late = json.dumps({**BASE, "event_timestamp": "2020-01-01T00:00:00Z"})
    frame = (
        raw_frame(
            spark,
            [
                (raw, "order-events"),
                (raw, "order-events"),
                (bad, "order-events"),
                (late, "order-events"),
            ],
        )
        .withColumn("scenario", F.lit("contract-fixture"))
        .withColumn("stream_run_id", F.lit("fixture-run"))
    )
    database = "retailpulse_contract_" + uuid4().hex
    spark.sql(f"CREATE DATABASE {database}")
    namespace = {
        "__name__": "__main__",
        "spark": spark,
        "DataFrame": DataFrame,
        "F": F,
        "json": json,
        "time": __import__("time"),
        "checkpoint_namespace": "fixture-checkpoint",
        "fail_after_committed_batch": True,
    }
    for kind in ("bronze", "silver", "quarantine", "audit"):
        namespace[f"{kind}_table"] = f"`spark_catalog`.`{database}`.`{kind}`"
        namespace[f"{kind}_path"] = str(tmp_path / kind)
    bundled = bundle_notebook(ROOT / "databricks" / "stream_bronze_silver.py")
    prelude = bundled.split("# RETAILPULSE_SHARED_CONTRACT_END", 1)[0]
    exec(compile(prelude, "bundled_prelude.py", "exec"), namespace)
    # Execute the actual notebook functions against local Delta. Excluding the
    # credential/widget setup makes this test offline without substituting merges.
    parsed = ast.parse(bundled)
    functions = [
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"ensure_external_table", "merge_frame", "process_batch"}
    ]
    exec(compile(ast.Module(body=functions, type_ignores=[]), "cloud_batch.py", "exec"), namespace)
    input_path = tmp_path / "input"
    input_path.mkdir()
    (input_path / "events.json").write_text("\n".join(frame.toJSON().collect()) + "\n")
    checkpoint = tmp_path / "checkpoint"

    def start():
        return (
            spark.readStream.schema(frame.schema)
            .json(str(input_path))
            .writeStream.foreachBatch(namespace["process_batch"])
            .option("checkpointLocation", str(checkpoint))
            .trigger(availableNow=True)
            .start()
        )

    query = None
    try:
        query = start()
        with pytest.raises(StreamingQueryException, match="INTENTIONAL_FAILURE_AFTER_COMMITTED"):
            query.awaitTermination(120)
        assert not (checkpoint / "commits" / "0").exists()
        first_audit = spark.table(namespace["audit_table"]).first()
        assert (
            first_audit.records_read,
            first_audit.records_written,
            first_audit.records_duplicate,
            first_audit.records_rejected,
        ) == (4, 1, 1, 2)
        namespace["fail_after_committed_batch"] = False
        query = start()
        assert query.awaitTermination(120)
        assert (checkpoint / "commits" / "0").exists()
        assert spark.table(namespace["bronze_table"]).count() == 4
        silver = spark.table(namespace["silver_table"]).collect()
        assert len(silver) == 1
        assert silver[0].price == "1.005"
        rejected = spark.table(namespace["quarantine_table"]).collect()
        assert {row.error_type for row in rejected} == {"SCHEMA_VALIDATION", "LATE_EVENT"}
        assert {row.raw_payload for row in rejected} == {bad, late}
        assert {row.offset for row in rejected} == {2, 3}
        assert all(row.source_topic == "order-events" and row.partition == 0 for row in rejected)
        audit = spark.table(namespace["audit_table"]).collect()
        assert len(audit) == 1
        assert audit[0].records_written == 0
        assert json.loads(audit[0].bronze_metrics_json)["numTargetRowsInserted"] == 0
        assert json.loads(audit[0].silver_metrics_json)["numTargetRowsInserted"] == 0
        assert json.loads(audit[0].quarantine_metrics_json)["numTargetRowsInserted"] == 0
        assert audit[0].records_duplicate == 2
        assert audit[0].records_read == (
            audit[0].records_written + audit[0].records_duplicate + audit[0].records_rejected
        )
        # A normal subsequent microbatch also contains a target match together
        # with a new ID. This is independent of interrupted checkpoint replay.
        next_frame = (
            raw_frame(
                spark,
                [
                    (raw, "order-events"),
                    (json.dumps({**BASE, "event_id": str(UUID(int=123))}), "order-events"),
                ],
            )
            .withColumn("offset", F.col("offset") + 4)
            .withColumn("scenario", F.lit("contract-fixture"))
            .withColumn("stream_run_id", F.lit("fixture-run"))
        )
        (input_path / "next.json").write_text("\n".join(next_frame.toJSON().collect()) + "\n")
        query = start()
        assert query.awaitTermination(120)
        next_audit = spark.table(namespace["audit_table"]).filter("batch_id = 1").first()
        assert (
            next_audit.records_read,
            next_audit.records_written,
            next_audit.records_duplicate,
            next_audit.records_rejected,
        ) == (2, 1, 1, 0)
        assert spark.table(namespace["bronze_table"]).count() == 6
        assert spark.table(namespace["silver_table"]).count() == 2
    finally:
        if query is not None and query.isActive:
            query.stop()
        spark.sql(f"DROP DATABASE {database} CASCADE")
