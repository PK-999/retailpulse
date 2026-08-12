# Rules-fallback duplicate incident report

Run ID: `0cf0a335-bcde-4262-b066-aefba0928cf1`

Incident: local_bronze_silver

Detected anomalous data quality in run 0cf0a335-bcde-4262-b066-aefba0928cf1:
duplicate_rate=26.7%.

Likely cause: events were likely replayed by a producer or consumer retry.

Recommended action: verify producer idempotency and retain event_id deduplication before MERGE.
Quarantined data remains available for replay.
