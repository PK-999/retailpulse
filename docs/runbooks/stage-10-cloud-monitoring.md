# Stage 10 cloud monitoring runbook

Status: prepared locally; live deployment and delivery remain unverified.
The [read-only preflight](../evidence/cloud-monitor-preflight.json) recorded ADF as `Disabled`
at `2026-10-04T18:29:01Z`. No failure alert exists, and the Terraform state account returns
`403 AccountIsDisabled`. Resolve those conditions before any deployment or attended test.

## Resource and cost scope

[monitoring.tf](../../terraform/monitoring.tf) adds the following resources only when
`enable_cloud_monitoring=true`. All monitoring flags default to false and the receiver map
defaults to empty.

| Resource | Condition | Configuration |
|---|---|---|
| ADF metric alert | Monitoring enabled | `PipelineFailedRuns`, Total greater than zero; 15-minute window; evaluate every 5 minutes; severity 2; automatic mitigation |
| Email action group | Monitoring enabled and `monitor_email_receivers` is nonempty | Only supplied recipient labels/addresses; common alert schema; no role-based recipients |
| ADF diagnostic setting | Monitoring enabled and `enable_adf_log_archive=true` | `PipelineRuns`, `ActivityRuns`, and `TriggerRuns` to the existing lake account |

The alert covers one ADF factory without dimension splitting. It detects pipeline execution
failure, not successful runs containing rejected, duplicate, late, or inconsistent data.
Those data-quality checks remain in the pipeline and local monitoring.
Microsoft lists `PipelineFailedRuns` as a Total metric sampled every minute.
[ADF supported metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-datafactory-factories-metrics).

The configuration uses the existing USD 10 monthly subscription budget. It sends cost
notifications; it does not stop consumption or enforce a spending cap. Check the current
billing currency, actual costs, remaining allowance, and budget in Cost Management before
the attended session. Budget evaluation is delayed, so it cannot bound this test in real time.
[Microsoft budget behavior](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

Azure Monitor charges metric alerts by monitored time series and notifications separately.
Microsoft currently lists ten included metric time series per month; the subscription's
remaining allowance has not been verified. Confirm applicable region/agreement pricing
before approval. This plan creates no Log Analytics workspace, compute, or Event Hubs.
The optional archive incurs storage capacity and transaction costs, and the single attended
ADF run can incur orchestration costs.
[Azure Monitor pricing](https://azure.microsoft.com/en-us/pricing/details/monitor/),
[ADF pricing](https://azure.microsoft.com/en-us/pricing/details/data-factory/data-pipeline/).

Storage diagnostics require a supported same-region destination and appropriate network
access. Terraform adds no retention policy: turning the diagnostic setting off stops future
exports but leaves existing log blobs and their storage costs. Record a retention/cleanup
date for diagnostic containers while preserving the project's lake data.
[Diagnostic destination requirements](https://learn.microsoft.com/en-us/azure/azure-monitor/data-collection/diagnostic-settings).

Creating an email receiver can itself send a confirmation or verification email. Obtain
explicit recipient consent before applying a nonempty receiver map. New receivers may need
to complete Microsoft's one-time-passcode verification within 30 minutes. Keep addresses in
an ignored local `.tfvars` file; Terraform state and saved plans can contain their values.
No receivers have been configured and no messages have been sent during this implementation.
[Microsoft action-group email behavior](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups).

## Restore service and state access

The account owner must investigate and resolve the disabled ADF/state-storage conditions.
Successful authentication or resource listing does not prove that workloads or state storage
are operational. Preserve the existing backend and resources; do not substitute a new state
account or apply an old saved plan to bypass the failure.

Confirm that ADF reports `Succeeded`, the existing backend can be read, and the current cost
position allows the reviewed session. From the repository root, the following state inspection
prints resource addresses without exporting state contents:

```bash
./scripts/terraform_azure.sh state list
```

## Run the read-only preflight

Use Python 3.11+ and an authenticated native Azure CLI. The verifier defaults to the repository's
`.azure` directory and performs only GET requests. It makes one account read and six resource
reads, with a 60-second overall deadline and at most 15 seconds per request.

```bash
AZURE_CONFIG_DIR="$PWD/.azure" python scripts/verify_cloud_monitoring.py \
  --preflight --output data/evidence/stage10/preflight.json
```

Exit 0 means that the factory is ready and the required metric is available. Preflight allows
an absent rule; `definition_verified=false` still means deployment has not been verified.
Exit 1 means readiness or definitions do not meet expectations. Exit 2 means an API/input
error prevented complete inspection. The current captured preflight exits 1.

The alert-state query reads the first page of up to 25 instances in the last day.
`inventory_complete=false` requires further read-only inspection before making an absence claim.
The verifier excludes unrelated resources/rules and never claims email or archive delivery.
Fixture mode (`--fixture path.json`) never contacts Azure and is labeled `offline_fixture`.

## Review a fresh Terraform plan

After restoration and a passing preflight, prepare the quiet alert-only plan first:

```bash
./scripts/terraform_azure.sh plan -var-file=dev.tfvars \
  -var='enable_cloud_monitoring=true' \
  -var='enable_adf_log_archive=false' \
  -var='monitor_email_receivers={}' \
  -out=stage10-monitoring.tfplan
./scripts/terraform_azure.sh show stage10-monitoring.tfplan
```

`dev.tfvars` must preserve the actual existing lifecycle settings. Reject unexplained changes
to the workspace, lake, identities, budget, or backend. The reviewed monitoring delta is one
metric alert, plus a diagnostic setting and/or action group only if explicitly selected.
Do not publish the saved plan or state. Confirm the remaining spend allowance, one-run limit,
receiver consent, and cleanup decision before attended execution.

## Attended deployment and one failure test

This section describes future authorized actions; none were performed in the recorded session.
After approval, apply the reviewed saved plan, then run the verifier without `--preflight`.
Use `--expect-diagnostics` if archival was selected and `--require-notifications` if authorized
receivers were selected. A successful definition check proves configuration, not firing or delivery.

For an attended proof, create a uniquely named, unscheduled ADF test pipeline with this single
activity. Use no linked services, data copying, Databricks jobs, or retry loop. Microsoft's Fail
activity permits a deliberate failure with a recognizable code/message.
[ADF Fail activity](https://learn.microsoft.com/en-us/azure/data-factory/control-flow-fail-activity).

```json
{
  "properties": {
    "activities": [
      {
        "name": "ExpectedMonitoringFailure",
        "type": "Fail",
        "typeProperties": {
          "errorCode": "RETAILPULSE_MONITOR_PROOF",
          "message": "RetailPulse attended monitoring proof"
        }
      }
    ],
    "annotations": ["RetailPulseMonitoringProof"]
  }
}
```

Execute it once and record its run ID, UTC start/end, terminal `Failed` state, and the expected
error code. Set a 45-minute attended observation deadline with no additional pipeline invocations.
Inspect the failed-run metric and matching alert using GET requests; save separate verifier
reports when `Fired` and `Resolved` are observed. The old failure must age out of the 15-minute
window, and stateful metric alert resolution needs healthy evaluations, so resolution is not
instantaneous. Acknowledge/Close changes the user response state and does not prove that the
metric condition resolved.
[Azure alert states](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview),
[Metric alert behavior](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-types).

If notifications were authorized, have the recipient confirm the actual failure notification
and its matching alert identity/time. Record a redacted receipt for both Fired and Resolved
notifications if received. An action-group test message is separate transport evidence and
does not prove this ADF rule fired. Receiver configuration, OTP confirmation, observed alert
state, and inbox receipt are separate evidence. Common-schema fields support correlation.
[Common alert schema](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-common-schema).

If the deadline expires, retain partial results and mark the missing proof unverified; do not
rerun the pipeline automatically. Remove the unique test pipeline after recording its result.
For the bounded demonstration, review a new plan returning `enable_cloud_monitoring=false`
and clearing receivers/archive flags, then apply only that reviewed cleanup. Verify that the
monitoring resources are absent, project resources remain, and any diagnostic log retention
obligation is recorded. Update the [evidence record](../evidence/stage-10-cloud-monitoring.md)
only with observed results.
