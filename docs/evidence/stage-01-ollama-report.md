# Ollama-backed duplicate incident report

Run ID: `2ddc5eca-6819-436b-98dd-c06746aa1f29`

Incident: local_bronze_silver

Evidence: duplicate_rate=26.7% in run 2ddc5eca-6819-436b-98dd-c06746aa1f29.

Likely cause: events were likely replayed by a producer or consumer retry.

Action: verify producer idempotency and retain event_id deduplication before MERGE.
