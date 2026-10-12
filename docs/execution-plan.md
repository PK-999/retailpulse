# Optional Azure integration plan

The current portfolio release follows the [local demo guide](demo-guide.md) without additional
Azure spending. This plan is a reference for a separately authorized cloud session. It does not
mark historical integrations as currently operating.

## Readiness gate

The last account check on **9 October 2026** reported a disabled subscription. Saved preflight
saw ADF `Disabled`; the last remote state access returned `AccountIsDisabled`. A supplied portal
warning forecast deletion on 11 October. Subsequent resource existence, lake/state backup,
teardown, and billing status have not been verified.

Before future cloud work:

1. Establish an enabled subscription and accessible existing state backend, or explicitly design
   a new deployment with separate configuration and state.
2. Use Python 3.11–3.13, an authenticated operator, and the existing reviewed identity boundary.
3. Review infrastructure drift, future teardown dates, service SKUs, and estimated spend.
4. Run the read-only [monitoring preflight](runbooks/stage-10-cloud-monitoring.md).
5. Review a concrete Terraform plan before any apply. The historical example variables are not
   a substitute for the actual environment configuration.

Account listing alone does not prove storage or workload health. Budgets notify; they do not
cap charges. The historical free-credit exception expired on 19 August.

## Stage sequence and evidence gates

| Stage | Runbook | Gate before claiming fresh verification |
|---|---|---|
| Identity and storage | [Stage 4](runbooks/stage-04-identity-storage.md) | Scoped positive/negative access tests and safe outputs |
| Historical ingestion | [Stage 5](runbooks/stage-05-historical-ingestion.md) | Two distinct successful ADF deliveries; archive hash/size and normalized entity counts |
| Batch Delta | [Stage 6](runbooks/stage-06-databricks-batch.md) | Typed Bronze/Silver, quarantine, exact reconciliation, zero-write replay |
| Streaming | [Stage 7](runbooks/stage-07-eventhubs-streaming.md) | All scenarios, shared contract, post-commit failure recovery, reconciled Delta/audit history |
| Analytics | [Stage 8](runbooks/stage-08-dbt-gold.md) | 37 dbt nodes, source/mart reconciliation, unchanged MERGEs, SCD2 history |
| Public snapshot | [Stage 9](runbooks/stage-09-bi-dashboard.md) | Five reconciliation checks, actual export time, public browser QA, confirmed warehouse STOPPED |
| Cloud monitoring | [Stage 10](runbooks/stage-10-cloud-monitoring.md) | A bounded failure produces matching Fired/Resolved evidence; any receiver/archive delivery checked separately |

Use fresh Stage 5 run IDs as the Stage 6 inputs. Select supported executables with
`RETAILPULSE_PYTHON_BIN` for Stages 7/9 and `RETAILPULSE_DBT_BIN` for Stage 8 when needed.

## Operational boundaries

- Use one reviewed environment and scoped managed identities; keep secret values outside Git,
  terminal recordings, notebooks, and public artifacts.
- Keep immutable deliveries and quarantine evidence. Record run IDs, table versions, and UTC
  timestamps for every claim.
- Stage 7 automatically applies its constrained Event Hubs plan and cleans up temporary secrets
  and hubs. Review its cost boundary before running it.
- Databricks compute and SQL warehouses are attended and bounded. Check managed-networking costs
  as well as workload compute; an idle workspace is not necessarily free.
- Keep the scheduled dbt workflow paused outside the proof session.
- Avoid repeated failure invocations while waiting for an alert. Notification delivery requires
  its own evidence, not merely a configured action group.

## Cloud closure

After an authorized session, stop compute, verify warehouse state, confirm temporary Event Hubs
and secrets are removed, review ongoing charges, and apply only a reviewed retain/destroy plan.
Preserve non-secret proof and the state needed for the agreed lifecycle. Capture a new Azure
walkthrough only after its target-service gates pass.

The [August evidence](evidence/README.md) and [deployment decision](decisions/azure-deployment.md)
remain historical references. Fresh Azure deployment, alert delivery, backup, and teardown are
still deferred or unverified; they are not gates for the completed local portfolio release.
