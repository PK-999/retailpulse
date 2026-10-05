# Stage 10 cloud monitoring evidence

Recorded: 2026-10-05 Asia/Kolkata.
Latest read-only preflight: `2026-10-05T01:58:45.691458+00:00`; ADF remains `Disabled`.
Status: local implementation verified; Azure deployment and delivery unverified.

## Current live observations

[cloud-monitor-preflight.json](cloud-monitor-preflight.json) is a sanitized `azure_read_only`
report from the live Azure APIs, not a fixture or local simulation.

| Check | Recorded result |
|---|---|
| Target | `adf-retailpulse-dev-rp999` |
| ADF provisioning state | `Disabled` |
| Failed-run metric | `PipelineFailedRuns`, Total at one-minute sampling available |
| Expected rule | `alert-retailpulse-dev-rp999-adf-failed-runs` missing |
| Notification configuration | No action group attached; zero configured email receivers |
| Diagnostic archive | Not requested; delivery unverified |
| Alert instances | Zero matching instances in the last-day query; returned page complete |
| Preflight readiness | `false`; expected verifier exit 1 |
| API inspection errors | None in the six GET requests |
| End-to-end alert test | Unverified |

A separate read-only Terraform backend access attempt returned `403 AccountIsDisabled`
from state storage. This backend condition is not checked by the monitoring verifier.
Authentication/resource listing succeeds, but that does not establish usable ADF or backend
state. The cause of the disabled service/account has not been established here.

No Terraform apply, paid pipeline execution, action-group creation/test, recipient email,
or alert-state mutation was performed for this stage.

## Locally verified implementation

[monitoring.tf](../../terraform/monitoring.tf) defines a default-off metric alert scoped to
one ADF factory. It evaluates Total `PipelineFailedRuns > 0` every five minutes over a
15-minute window, with severity 2 and automatic mitigation. No dimension fanout is configured.
Optional ADF run-log archival uses the existing lake; it creates no Log Analytics workspace.
An email action group is created only when monitoring is enabled and an operator supplies
explicit recipients. The empty default has no notification actions.

The [verifier](../../scripts/verify_cloud_monitoring.py) checks resource readiness, metric
availability, rule scope/condition, optional archive destination/categories, action-group
configuration, and matching observed alert states. Requests are bounded to 60 seconds in total.
Reports omit recipient addresses and subscription IDs; delivery remains `unverified` even
when a fixture contains a Fired alert and a valid receiver definition.

Validation performed:

- Terraform `fmt -check` and `validate` passed with `retailpulse-azure-tools:1.15.8` and
  cached AzureRM `5.0.1` in an isolated copy with the remote backend excluded.
  This proves configuration/schema validity, not a live plan or deployability.
- All 14 [behavioral verifier cases](../../tests/test_cloud_monitoring.py) passed after
  an initial failing run. They cover threshold/aggregation/scope drift, dimension fanout,
  disabled factories, missing definitions, optional archive completeness, required receivers,
  unrelated alert exclusion, pagination, and the distinction between configuration and delivery.
- Ruff passed for the verifier and its tests.

## Cost and remaining proof

Terraform's monthly budget defaults to USD 10. The currently available credit, billing currency,
live budget state, and remaining free alert allowance were not verified by this preflight.
Budgets notify and do not cap charges. Microsoft currently lists ten included metric time
series per month; notifications and archival storage have separate cost considerations.
[Microsoft budget behavior](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets),
[Azure Monitor pricing](https://azure.microsoft.com/en-us/pricing/details/monitor/).

The [attended runbook](../runbooks/stage-10-cloud-monitoring.md) requires this sequence:

1. Restore ADF and state-account access through the account owner.
2. Pass fresh read-only readiness checks and confirm the current cost position.
3. Review a fresh saved Terraform plan preserving unrelated resources; explicitly select
   diagnostics and recipients if wanted. Creating email receivers can send confirmation/OTP
   emails, so recipient consent precedes that apply.
4. Perform the authorized attended deployment and verify its definitions.
5. Execute one isolated, unscheduled Fail-activity pipeline; capture its failure and the metric.
6. Capture the matching alert's Fired and Resolved observations, then separately capture
   confirmed recipient receipt and any archived log delivery.
7. Finish the reviewed cleanup and record retained diagnostic-log obligations.

Until that sequence is completed, the following claims remain unverified:

| Claim | Required evidence |
|---|---|
| Alert deployed | Successful live plan/apply and matching definition verification |
| ADF failure detected | Attended test run ID/error and corresponding metric observation |
| Rule fired | Matching factory/rule alert instance and Fired timestamp |
| Condition recovered | Matching instance transitioned to Resolved; acknowledgement alone is insufficient |
| Notification delivered | Recipient-confirmed, redacted receipt correlated to the actual alert |
| Logs archived | Actual storage object correlated to the attended run; setting existence is insufficient |

Microsoft documents the metric and log categories used here, as well as action-group receiver
confirmation/verification behavior. These references support the design; they are not live
RetailPulse delivery evidence.
[ADF metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/microsoft-datafactory-factories-metrics),
[ADF logs](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-logs/microsoft-datafactory-factories-logs),
[Action groups](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups).
