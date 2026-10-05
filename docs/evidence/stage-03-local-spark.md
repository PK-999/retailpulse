# Stage 3 local Spark/Delta verification

Verification date: 2026-08-12
Status: passed

## Runtime

- Reproducible Compose runner built from `tools/Dockerfile.spark`.
- Python 3.11.13.
- OpenJDK 17.0.20.
- PySpark 4.0.4 and Delta Lake 4.0.0.
- Redpanda healthy with zero leaderless or under-replicated partitions.
- Three topics with three partitions each: `customer-events`, `order-events`, and
  `inventory-events`.
- Streaming trigger: `AvailableNow`.

## Input

The broker retained the earlier 30-event Stage 1 sample. Stage 3 added 30 normal events, eight
malformed-scenario records, twelve duplicate-scenario records, and one later incremental normal
event. Before the incremental delivery, the first bounded pass therefore read 80 broker records.

## First bounded pass

- Checkpoint namespace: `stage3-first`.
- Bronze rows: 80. Bronze retained valid, malformed, and replayed records.
- Quarantine rows: 2. The malformed generator emits invalid JSON at indexes zero and four.
- Silver rows: 75. Two malformed rows and three repeated event IDs did not become Silver rows.
- Bronze, Silver, and quarantine checkpoint directories all existed.
- Initial Silver Delta version: 0, operation `WRITE`, 75 output rows.

## Incremental MERGE

After one new normal event was published, the original checkpoint resumed from its stored Kafka
offsets. `foreachBatch` received one row with an existing Delta target. Delta version 1 recorded a
`MERGE` with:

- source rows: 1;
- target rows inserted: 1;
- target rows updated/deleted/copied: 0;
- resulting Silver rows: 76.

## Idempotent replay

A fresh `stage3-idempotency` checkpoint replayed all 81 broker records from earliest. The Silver
batch deduplicated those records to 76 event IDs and invoked the MERGE against the existing target.
Every source ID already existed, so Delta optimized the all-matched operation into a no-op: no new
Delta version was created, version 1 remained latest, and Silver remained exactly 76 rows.

The replay appended raw evidence again by design, resulting in 322 Bronze rows across the four
independent checkpoint namespaces used during verification. Quarantine likewise retained eight
raw invalid occurrences. This is expected for independent full replays; the Silver event-ID MERGE
is the idempotency boundary.

## Result

The local Kafka transport, Spark Structured Streaming source, `AvailableNow` termination,
checkpoint creation/resume, raw Bronze retention, malformed quarantine, Delta MERGE, incremental
insert, and full-replay idempotency are externally verified.
