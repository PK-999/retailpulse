# Stage 4 identity and storage readiness

Verification date: 2026-08-12
Status: complete

## Built

- A system-assigned Databricks Access Connector.
- Premium workspace tier selected because Unity Catalog requires it; no compute is defined.
- Filesystem-scoped Storage Blob Data Contributor assignments for ADF and the connector.
- Key Vault Secrets User for ADF and Secrets Officer for the deployment identity.
- `landing`, `bronze`, `silver`, `gold`, `checkpoints`, and `quarantine` directory resources.
- Non-secret outputs for ABFSS URL, identity IDs, connector ID, paths, and the Event Hubs secret name.
- Unity Catalog storage-credential/external-location templates and a Delta write/read test notebook.
- A secret-upload helper that refuses secret files located inside the repository.
- A positive/negative access verification runbook and versioned access matrix.

## Live verification

- Terraform applied the identity/storage resources and a closing plan reported no drift.
- The ADF and Access Connector identities both retain Storage Blob Data Contributor at the
  `retailpulse` filesystem scope.
- The Access Connector also has Storage Blob Delegator at storage-account scope. The first Delta
  test exposed this documented Unity Catalog requirement; the correction added one role, changed
  nothing, and destroyed nothing.
- ADF pipeline runs `c4f862ec-9628-11f1-865a-1ec70f388fba` and
  `5e9f8eb0-962a-11f1-988a-b262b486c5ef` succeeded and wrote the public project README to
  `landing/_access_tests/stage-04-adf/README.md` using the factory managed identity. The second run
  verified the finalized placeholder-based deployment script.
- Unity Catalog storage credential and external location `retailpulse_dev_lake` use the Access
  Connector and the project filesystem URL. No secret or storage key is stored in the credential.
  The location currently uses open workspace isolation; the subscription has only this Databricks
  workspace. Change it to isolated and add an explicit workspace binding before attaching another
  workspace to the metastore.
- The bounded Databricks SQL proof created an external Delta table, performed an idempotent MERGE,
  and reconciled exactly one verification row. The `_delta_log` path exists in ADLS.
- The platform-created serverless starter warehouse was explicitly stopped after the test and was
  verified `STOPPED` with zero active clusters.
- Negative test: the existing operator identity, which has no Storage Blob data role, was denied
  when listing the filesystem with `--auth-mode login`. No access was removed to simulate denial.

## Secret boundary

Event Hubs is disabled and no SAS credential exists, so no Event Hubs value was added to Key Vault.
The secret name and upload helper remain ready for the bounded Stage 7 streaming session. This is
the intended state, not an incomplete Stage 4 secret test.

## Reproducible assets

- `scripts/run_stage04_adf_test.sh` deploys the versioned ADF linked services, datasets, and access
  pipeline, then waits for a terminal run state.
- `scripts/run_stage04_databricks_sql_test.sh` performs the bounded Delta proof and always requests
  warehouse stop on exit.
- `docs/security/access-matrix.md` records scopes and intended access without principal IDs.

## Closing validation

- Fresh Terraform drift plan: no changes.
- Terraform format and validation: passed.
- Python tests: 18 passed.
- Ruff, Docker Compose validation, shell syntax, and all Stage 4 ADF JSON parsing: passed.
- Repository diff whitespace and private-key/connection-secret pattern checks: passed.
- Azure compute boundary: starter SQL warehouse stopped, no classic clusters, and no Event Hubs
  namespace.
