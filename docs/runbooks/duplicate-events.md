# Duplicate event runbook

Trigger: `duplicate_rate > 5%` in one pipeline run.

1. Confirm that duplicate `event_id` values exist in the Bronze table.
2. Compare Kafka topic, partition, and offset to distinguish broker replay from producer replay.
3. Verify the producer has idempotence enabled and uses a stable event ID for retries.
4. Keep event-ID deduplication in the source batch and Silver MERGE. Late events are explicitly
   quarantined against ingestion time; a Spark stateful watermark must not silently discard them.
5. Replay only quarantined or failed offsets after the upstream cause is resolved.

Never delete Bronze records during remediation; Bronze is the replayable audit trail.
