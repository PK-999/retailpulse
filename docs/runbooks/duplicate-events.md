# Duplicate event runbook

Trigger: `duplicate_rate > 5%` in one pipeline run.

1. Confirm that duplicate `event_id` values exist in the Bronze table.
2. Compare Kafka topic, partition, and offset to distinguish broker replay from producer replay.
3. Verify the producer has idempotence enabled and uses a stable event ID for retries.
4. Keep Silver's watermark and `dropDuplicates(["event_id"])` before Delta MERGE.
5. Replay only quarantined or failed offsets after the upstream cause is resolved.

Never delete Bronze records during remediation; Bronze is the replayable audit trail.
