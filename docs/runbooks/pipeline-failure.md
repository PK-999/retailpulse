# Local pipeline failure and recovery

Trigger: `RetailPulsePipelineFailed` or `pipeline_failure` in the metrics snapshot.

1. Inspect `retailpulse status` and the exception. A failed run records attempted row counts;
   they do not prove its transaction committed. SQLite `source_offsets` is the input authority.
2. Restore storage access and keep the original inbox files intact. A changed or truncated
   committed prefix is an error; do not reset checkpoints to hide it.
3. Run `retailpulse process`. Uncommitted input is classified again; committed input is skipped.
   Bronze, Silver, quarantine, audit JSONL, and checkpoint files are regenerated from SQLite.
4. Confirm successful audit, matching source totals and repaired exports, then rebuild dbt Gold.
   A successful run publishes `retailpulse_pipeline_failed 0`; Prometheus resolves the alert.

An abrupt exit leaves `RUNNING` before commit or `COMMITTED` after commit. Recovery marks these
`INTERRUPTED` or `RECOVERED`. The local adapter assumes one attended writer and completed,
append-only inbox deliveries. It is an operational reference, not a distributed transaction
across all exported files. The failure-boundary tests use real subprocess exits.
