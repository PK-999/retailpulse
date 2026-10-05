"""Exact Python event validation for local and self-contained Databricks Spark jobs.

The UDF captures source text, never an import of the project on an executor. Each
worker reconstructs the current Pydantic model once. This favors contract parity
over throughput for the bounded demo; larger streams should benchmark this UDF.
New Silver tables keep canonical Decimal text. Existing decimal tables reject
unrepresentable values explicitly, rather than silently round or overflow them.
"""


def read_contract_source() -> str:
    from pathlib import Path

    return Path(__file__).with_name("contracts.py").read_text(encoding="utf-8")


def make_event_validator(
    contract_source: str,
    *,
    decimal_precision: int | None = None,
    decimal_scale: int | None = None,
):
    """Return a worker-safe callable; Pydantic is the only executor dependency."""

    def validate(raw_payload: str, topic: str) -> dict:
        # Keep every dependency inside the closure so the bundled notebook works
        # on isolated executors without the retailpulse package or workspace files.
        import hashlib
        import json
        import sys
        import types
        from decimal import Decimal, InvalidOperation, localcontext

        from pydantic import ValidationError

        module_name = (
            "_retailpulse_contract_"
            + hashlib.sha256(contract_source.encode("utf-8")).hexdigest()[:16]
        )
        runtime = sys.modules.get(module_name)
        if runtime is None:
            runtime = types.ModuleType(module_name)
            sys.modules[module_name] = runtime
            exec(compile(contract_source, "retailpulse_contract.py", "exec"), runtime.__dict__)

        result = {
            name: None
            for name in (
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
                "error_type",
                "error_message",
            )
        }
        try:
            event = runtime.RetailEvent.model_validate_json(raw_payload)
        except (ValidationError, ValueError) as error:
            try:
                payload = json.loads(raw_payload)
                if isinstance(payload, dict) and isinstance(payload.get("event_id"), str):
                    result["event_id"] = payload["event_id"]
            except (ValueError, TypeError):
                pass
            result["error_type"] = "SCHEMA_VALIDATION"
            if isinstance(error, ValidationError):
                result["error_message"] = "; ".join(
                    f"{'.'.join(map(str, item['loc'])) or 'payload'}: {item['msg']}"
                    for item in error.errors(
                        include_url=False, include_context=False, include_input=False
                    )
                )
            else:
                result["error_message"] = str(error)
            return result

        result.update(event.model_dump())
        result["event_id"] = str(event.event_id)
        # TimestampType uses UTC calendar.timegm for aware values; naive values
        # depend on the executor's OS timezone and can change lateness decisions.
        result["event_timestamp"] = event.event_timestamp
        result["price"] = str(event.price) if event.price is not None else None
        expected_topic = runtime.TOPIC_BY_EVENT[event.event_type]
        if topic != expected_topic:
            result["error_type"] = "TOPIC_MISMATCH"
            result["error_message"] = f"{event.event_type} must use {expected_topic}"
            return result

        # Defensive representation checks also protect jobs against an older core
        # contract being bundled accidentally. Never let Spark convert to null.
        if event.quantity is not None and not -(2**31) <= event.quantity < 2**31:
            result["quantity"] = None
            result["error_type"] = "SILVER_REPRESENTATION"
            result["error_message"] = "quantity cannot be represented by Silver INT32"
            return result
        if event.price is not None and decimal_precision is not None:
            scale = decimal_scale or 0
            with localcontext() as context:
                context.prec = (
                    max(decimal_precision, len(event.price.as_tuple().digits)) + scale + 2
                )
                try:
                    exact = event.price.quantize(Decimal(1).scaleb(-scale)) == event.price
                    within_range = event.price < Decimal(10) ** (decimal_precision - scale)
                except InvalidOperation:
                    exact = within_range = False
            if not exact or not within_range:
                result["error_type"] = "SILVER_REPRESENTATION"
                result["error_message"] = (
                    f"price cannot be represented exactly by existing Silver "
                    f"DECIMAL({decimal_precision},{scale}); use a new string-price Silver table"
                )
                # Prevent downstream ANSI casts from trying an invalid value.
                result["price"] = None
        return result

    return validate


def classify_events(raw, contract_source: str, *, topic_column: str = "topic", price_type=None):
    """Preserve every source field and classify schema, topic, and lateness failures."""
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        DecimalType,
        IntegerType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    decimal_options = (
        {"decimal_precision": price_type.precision, "decimal_scale": price_type.scale}
        if isinstance(price_type, DecimalType)
        else {}
    )
    schema = StructType(
        [
            StructField("event_id", StringType()),
            StructField("event_type", StringType()),
            StructField("customer_id", StringType()),
            StructField("product_id", StringType()),
            StructField("order_id", StringType()),
            StructField("quantity", IntegerType()),
            StructField("price", StringType()),
            StructField("country", StringType()),
            StructField("query", StringType()),
            StructField("event_timestamp", TimestampType()),
            StructField("schema_version", IntegerType()),
            StructField("error_type", StringType()),
            StructField("error_message", StringType()),
        ]
    )
    validate = F.udf(make_event_validator(contract_source, **decimal_options), schema)
    parsed = (
        raw.withColumn("_validated_event", validate("raw_payload", topic_column))
        .select("*", "_validated_event.*")
        .drop("_validated_event")
    )
    if isinstance(price_type, DecimalType):
        parsed = parsed.withColumn("price", F.col("price").cast(price_type))
    late = F.col("error_type").isNull() & (
        F.col("event_timestamp") < F.col("ingestion_timestamp") - F.expr("INTERVAL 30 MINUTES")
    )
    return parsed.withColumn(
        "error_message",
        F.when(late, F.lit("event_timestamp is older than the 30-minute watermark")).otherwise(
            F.col("error_message")
        ),
    ).withColumn("error_type", F.when(late, F.lit("LATE_EVENT")).otherwise(F.col("error_type")))


# NOTEBOOK_BUNDLE_EXCLUDE
def bundle_notebook(notebook_path) -> str:
    """Inline this helper and the current core contract into the upload artifact."""
    from pathlib import Path

    marker = "# RETAILPULSE_SHARED_CONTRACT"
    notebook = Path(notebook_path).read_text(encoding="utf-8")
    if notebook.count(marker) != 1:
        raise ValueError("notebook must contain exactly one shared-contract marker")
    helper = Path(__file__).read_text(encoding="utf-8").split("# NOTEBOOK_BUNDLE_EXCLUDE", 1)[0]
    prelude = (
        "# Generated from retailpulse.contracts and retailpulse.spark_contract.\n"
        f"RETAILPULSE_CONTRACT_SOURCE = {read_contract_source()!r}\n"
        f"{helper}\n# RETAILPULSE_SHARED_CONTRACT_END"
    )
    return notebook.replace(marker, prelude)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Emit a self-contained Stage 7 notebook.")
    parser.add_argument("--notebook", required=True)
    args = parser.parse_args()
    print(bundle_notebook(args.notebook))


if __name__ == "__main__":
    main()
