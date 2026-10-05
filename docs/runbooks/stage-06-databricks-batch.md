# Stage 6 Databricks historical-batch runbook

## Run

From an Azure-authenticated checkout whose Stage 3–5 resources and normalized deliveries still
exist:

```bash
./scripts/run_stage06_databricks_batch.sh
```

The command uploads the notebook, creates or resets one unscheduled serverless job, runs the two
known immutable Stage 5 deliveries, and validates:

- the second run adds exactly one deliberate rejection to the observed source-quality baseline;
- valid-record counts and all Silver totals are stable;
- the injected rejection is isolated to order items;
- Query History contains statements and no failed statement for either successful task.

The job has one-run concurrency, no retry, `STANDARD` performance, and a 30-minute timeout. It does
not create an all-purpose cluster, Event Hubs namespace, ADF trigger, or SQL warehouse.

## Override delivery or catalog references

Use existing successful Stage 5 ADF run IDs and the deployed Unity Catalog name:

```bash
RETAILPULSE_STAGE6_FIRST_ADF_RUN_ID=<first-adf-run-id> \
RETAILPULSE_STAGE6_SECOND_ADF_RUN_ID=<second-adf-run-id> \
RETAILPULSE_DATABRICKS_CATALOG=<catalog-name> \
  ./scripts/run_stage06_databricks_batch.sh
```

The delivery IDs must differ and both normalized paths must already exist. Reusing the verified
pair is safe: pipeline-run/hash MERGEs make Bronze, quarantine, and audit idempotent for the same
delivery IDs, while Silver is keyed by business records.

## Success gate

- Both notebook results report `STAGE6_BATCH_OK`.
- The second run has one more rejection than the first and the same valid-record count.
- Every Silver table has the same total after both runs; second-run Delta metrics write zero Silver
  rows.
- Quarantine and audit totals reconcile by pipeline run ID.
- Query History has at least one statement and zero failed statements for each task run.
- Active job runs and classic clusters are empty and the starter warehouse remains stopped.
