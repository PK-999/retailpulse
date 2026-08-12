# Stage 5 historical-ingestion runbook

## Run

From an authenticated checkout whose Stage 3/4 Terraform outputs still point to the live Azure
environment:

```bash
./scripts/run_stage05_historical_ingestion.sh
```

The command deploys/updates the ADF assets and the single unscheduled Databricks serverless job,
then runs two deliveries and reconciles their normalized counts. It does not create an ADF trigger,
classic cluster, or SQL warehouse.

## Resume after a local interruption

If ADF succeeded but local orchestration stopped before normalization, reuse the successful raw
delivery instead of copying it again:

```bash
RETAILPULSE_STAGE5_RESUME_ADF_RUN_ID=<successful-adf-run-id> \
  ./scripts/run_stage05_historical_ingestion.sh
```

The script confirms that the supplied ADF run succeeded before reusing its immutable raw path.

To validate an already-normalized delivery without creating a second ADF delivery, add the
verification-only flag:

```bash
RETAILPULSE_STAGE5_RESUME_ADF_RUN_ID=<successful-adf-run-id> \
RETAILPULSE_STAGE5_VERIFY_EXISTING_ONLY=true \
  ./scripts/run_stage05_historical_ingestion.sh
```

This path must return `idempotent_reuse=true`; it recounts the existing datasets and performs no
data writes.

## Success gate

- Two different ADF run IDs report `Succeeded`.
- Both task results report the expected source size and SHA-256.
- Both outputs contain customers, products, orders, and order-items with equal counts.
- Raw and normalized roots contain their corresponding ADF run IDs.
- Active job runs, classic clusters, and ADF triggers are empty; any starter SQL warehouse is
  stopped.

Do not grant the deployment operator a broad storage data role merely to inspect files. Use the
authorized ADF/Databricks outputs and manifests, preserving the negative-access proof from Stage 4.
