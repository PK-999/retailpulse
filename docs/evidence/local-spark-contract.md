# Local Spark event contract verification

Verified on 2026-10-04 UTC / 2026-10-05 Asia/Kolkata. This evidence covers local
execution and offline execution of the Databricks transformation functions. The
updated notebook has not been run on paid Databricks compute.

## Runtime and reproducible contract suite

The fresh `retailpulse-spark-runner:contract-ci` image contains Python 3.11.13,
PySpark 4.0.4, Delta Lake 4.0.0, OpenJDK 17.0.20, and Pydantic 2.13.5. Its build
resolves the Delta and Kafka connector jars in advance; the fixture suite needs
no runtime Maven access or separately populated Ivy volume.

```sh
docker build -f tools/Dockerfile.spark -t retailpulse-spark-runner:contract-ci .
docker run --rm --network none --hostname localhost \
  -e SPARK_LOCAL_IP=127.0.0.1 -e PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  -v "$PWD:/work:ro" retailpulse-spark-runner:contract-ci \
  python -m pytest tests/test_spark_contract.py -p no:cacheprovider
```

Result: **46 passed in 23.04 seconds**. Executors use `TZ=Asia/Kolkata` in the
fixture session. The regression test verifies that UTC event instants remain
unchanged and that an event at the 30-minute boundary is accepted. Returning an
aware UTC timestamp from the UDF fixed the previously observed timezone shift
and incorrect late-event classification.

The host-only contract suite passed 42 tests and skipped four requiring PySpark.
Including the six Stage 7 asset checks produced 48 passed and four skipped.
Those host skips are separate from the successful actual Spark run.
The final complete Python suite passed 168 tests and skipped the same four
Spark-dependent tests in 54.15 seconds.

The actual Spark fixtures exercise structured schema/business failures, malformed
JSON, wrong topics, late-event retention, exact Decimal text, and isolated worker
execution without the `retailpulse` package. They also execute the real notebook
`process_batch` functions through a file-backed streaming source and local Delta.
An intentional failure after committed Bronze, quarantine, Silver, and audit
merges is followed by a successful restart using the same checkpoint. The replay
retains four Bronze rows, one Silver event, and two quarantine rows, and reports
zero new inserts. The test caught and fixed a batch-session temporary-view
mismatch and stale audit metrics when Delta does not commit a no-op MERGE.

The final review regression also proves classification counts against actual
MERGE insertions, including IDs already present in Silver. All 46 Spark tests
passed after this correction in 25.18 seconds.

| Attempt | Read | Written | Duplicate | Rejected |
| --- | ---: | ---: | ---: | ---: |
| Initial batch, before intentional failure | 4 | 1 | 1 | 2 |
| Same-checkpoint recovery | 4 | 0 | 2 | 2 |
| Subsequent batch with one old and one new ID | 2 | 1 | 1 | 0 |

Every row reconciles `read = written + duplicate + rejected`. After the last
batch, Delta contains six Bronze rows, two Silver IDs, and two quarantine rows.

## Actual Kafka entrypoint and checkpoint resume

A private Docker network and a cached Redpanda v24.1.12 broker were used, with
no published host ports. The ordinary local entrypoint ran with `available-now`,
`--max-runtime-minutes 2`, `--base-path /fixture`, and the default
`local-contract-v2` checkpoint namespace.

The broker received 16 hand-built records: two copies of one valid purchase,
eleven structured contract violations, one wrong-topic purchase, one valid event
over an hour old, and one malformed JSON payload.

| Measurement | Initial run | Resume same checkpoints |
| --- | ---: | ---: |
| Bronze raw records | 16 | 16 |
| Silver unique events | 1 | 1 |
| Quarantine records | 14 | 14 |
| Latest Silver Delta version | 0 | 0 |

All three checkpoint directories existed. No events were republished before the
resume. The complete machine-readable summaries were asserted equal, including
Silver history; no new Silver commit was created.

A separate offline Delta read asserted these quarantine reasons:

| Reason | Records |
| --- | ---: |
| `SCHEMA_VALIDATION` | 12 |
| `TOPIC_MISMATCH` | 1 |
| `LATE_EVENT` | 1 |

Bronze and quarantine retained non-null topic, partition, offset, and Kafka
timestamp. Quarantine also retained every rejected raw payload and a failure
message. The accepted Silver purchase retained quantity `2` and price `1.005`
in a string column, with no implicit two-decimal rounding. The initial run used
the earlier cached image with Pydantic 2.13.4; the checkpoint resume and final
offline Delta inspection used the fresh image with Pydantic 2.13.5.

The temporary `retailpulse-contract-redpanda` broker and
`retailpulse-contract-kafka-net` network were removed after verification. The
separate `retailpulse-release-20261005` monitoring stack and existing project
data were not changed by these fixtures.

## Shared validation and cloud shipping

Both jobs validate against the current `RetailEvent` source, including UUIDs,
known event types, explicit integer version 1, timezone-aware ISO timestamps,
forbidden extra fields, required nonblank product/order IDs, strict Int32
quantities, finite nonnegative prices, and topic matching. Valid old events are
retained in quarantine rather than silently dropped by stateful deduplication.
New Silver tables preserve the complete canonical Decimal text. An existing
decimal-price target accepts only exactly representable prices; other values
are retained with `SILVER_REPRESENTATION` and a specific reason.

The Stage 7 helper emits a self-contained notebook with:

```sh
python -m retailpulse.spark_contract \
  --notebook databricks/stream_bronze_silver.py
```

Before workspace upload, it replaces the explicit shared-contract marker with
the current model source and Spark helper source. The UDF captures source text
and initializes the model on each worker, so it needs no project import or
driver-only workspace path. The Databricks job separately pins Pydantic 2.13.4;
the image's Pydantic 2.13.5 does not change that job environment. Compilation,
isolated-worker execution, and the transformation/recovery logic are verified
locally. Updated live Event Hubs/Databricks execution remains unverified.

The per-row Python/Pydantic UDF and repeated batch actions suit the bounded
proof. These fixtures establish correctness, not a Spark throughput SLA.

## Separate bounded file/SQLite benchmark

[Machine-readable benchmark](local-scale-benchmark.json) records one fresh,
temporary-directory run of 50,000 normal events with seed 42 on Darwin arm64,
Python 3.13.15, and Pydantic 2.12.5. It excludes Kafka, Spark, dbt, and cloud.

| Operation | Seconds |
| --- | ---: |
| Generate 50,000 file-backed events | 3.423270 |
| First process, including classification exports | 1.550201 |
| First Gold rebuild | 0.043382 |
| No-op process | 0.670049 |
| No-op Gold rebuild | 0.044230 |

Both runs retained 50,000 Bronze and 50,000 Silver records, with zero quarantine.
The no-op reported zero records read/written, byte-identical classification
exports, and unchanged Gold totals. Inbox size was 13,515,927 bytes; complete
classification exports occupied 44,561,390 bytes.

A no-op still scans and hashes committed input prefixes and rewrites complete
Bronze, Silver, and quarantine snapshots. Its cost grows with retained history;
zero new records does not mean constant-time execution. This single observation
is a bounded local benchmark, not a capacity or latency guarantee. Its temporary
data directory was removed after successful verification.
