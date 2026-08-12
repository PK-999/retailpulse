# Malformed event runbook

Trigger: `rejection_rate > 2%` or a schema-validation alert.

1. Group quarantine rows by schema version and validation error.
2. Check whether a producer deployed an uncoordinated contract change.
3. If the change is intentional, publish a backward-compatible schema version and update consumers.
4. If accidental, roll back the producer and replay quarantined records after correction.
