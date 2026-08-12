# Stage 7 Event Hubs streaming and checkpoint-recovery evidence

Verification date: 2026-08-12
Status: complete

## Live boundary and authentication

- Terraform enable plan: four creates, zero changes, zero destroys—one Standard Event Hubs
  namespace and `customer-events`, `order-events`, and `inventory-events`.
- Namespace rule `retailpulse-streaming` had `Listen` and `Send` only.
- The Python `confluent-kafka` producer used `SASL_SSL`, PLAIN, `acks=all`, idempotence, a 60-second
  request timeout, and scenario/session headers.
- The Databricks source loaded the session-specific connection string from a temporary
  Databricks-backed secret scope. Only scope/key names appeared in job parameters.
- Successful stream session ID: `597e4f88-a739-4467-81d4-901f14d8cb56`.
- Unscheduled job `retailpulse-stage07-eventhubs-streaming`, ID `255775269156497`, used
  `STANDARD` serverless compute, no retries, one-run concurrency, and a 30-minute timeout.

## Scenario reconciliation

| Scenario | Bronze | Silver | Quarantine |
|---|---:|---:|---:|
| normal | 60 | 60 | 0 |
| duplicate | 60 | 41 | 0 |
| late-data | 60 | 40 | 20 |
| malformed | 40 | 30 | 10 |
| traffic-spike | 200 | 200 | 0 |
| checkpoint-recovery | 40 | 40 | 0 |
| **Total** | **460** | **411** | **30** |

Silver contains 411 distinct event IDs. Batch 0 read 420 records, inserted 371 Silver rows,
quarantined 30, and identified 19 duplicate records. Bronze retained topic, partition, offset,
Kafka timestamp, ingestion timestamp, raw payload, scenario, session ID, and checkpoint namespace.

The live recovery output reported checkpoint batch 1 and watermark
`2026-08-12T12:10:54.340Z`. Its trigger duration was 51.412 seconds. Audit batch metrics recorded
average event-time latency 532,037.75 ms for the initial backlog and 489,459.03 ms for the recovery
batch; these values include Event Hubs publication-to-serverless execution wait, not only Spark
processing time.

## Checkpoint and Delta MERGE proof

| Phase | Parent job run | Task run | Setup | Execution | Result |
|---|---:|---:|---:|---:|---|
| Five scenarios | `273460583637895` | `293720607656610` | 265 s | 319 s | Success |
| Post-commit/pre-checkpoint fault | `205564099695222` | `311802766515259` | — | — | Expected failure |
| Same-checkpoint recovery | `867328480378469` | `868258908926524` | 195 s | 350 s | Success |
| Durable read-only verification | `624951804109027` | `1047741469612244` | 195 s | 265 s | Success |
| Final transport-metadata verification | `798987876842967` | `183713305698871` | — | — | Success |

The fault run committed the 40 recovery records to Delta and then raised the exact intentional
marker before Spark committed checkpoint batch 1. The next `AvailableNow` run reused the same
checkpoint and reread 40 source records. Durable audit evidence from that replay shows:

- Bronze MERGE version 3: 40 source rows, zero inserted/output rows, zero added/removed files.
- Silver MERGE version 3: 40 source rows, zero inserted/output rows, zero added/removed files.
- Quarantine MERGE version 3: zero source and inserted rows.
- Audit has two logical rows, batch IDs 0 and 1; replay updates batch 1 with the final no-op metrics.

This proves transport-coordinate Bronze idempotency, `event_id` Silver idempotency, and checkpoint
recovery without a multi-match MERGE failure.
The final verifier also returned `transport_metadata_nulls=0` across all 460 Bronze records.

## Operational issues fixed during verification

1. The containerized Azure CLI could not read a host `/var/folders/...` temporary secret file.
   The runner now uses a randomized mode-0600 file under ignored `.azure/`, which is mounted into
   the CLI container and deleted by the cleanup trap.
2. Databricks serverless shades its Kafka client. The JAAS class must use
   `kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule`; a regression test now
   enforces it.
3. Spark Connect does not propagate mutations to a driver-local Python list from `foreachBatch`.
   The notebook and runner now read durable audit rows for metrics and replay assertions.

The first two failed sessions never read Kafka offsets or wrote streaming Delta data, and each
cleanup check showed an empty Event Hubs namespace list plus a drift-free Terraform plan.

## Cost and security closure

- Event Hubs namespace: deleted.
- Temporary Databricks secret scope: deleted.
- Session-specific Key Vault secret: deleted (soft-deleted by vault policy).
- Active Databricks runs: none after the verification job.
- Classic clusters: none; starter SQL warehouse remained stopped.
- ADF triggers: none.
- Final Terraform plan: no changes.

## Reproducible assets

- `src/retailpulse/config.py`
- `src/retailpulse/producer.py`
- `databricks/stream_bronze_silver.py`
- `databricks/verify_stage07.py`
- `scripts/run_stage07_eventhubs_streaming.sh`
- `tests/test_producer.py`
- `tests/test_stage07_assets.py`
- `docs/runbooks/stage-07-eventhubs-streaming.md`
