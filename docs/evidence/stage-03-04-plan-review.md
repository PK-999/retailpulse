# Stage 3/4 minimal-cost Azure plan review

Review date: 2026-08-12
Status: applied successfully; post-apply verification found one provider-managed cost item

## Deployment preparation completed

- The six explicitly required Azure resource providers are registered.
- Remote state exists in the private `tfstate` container in the dedicated state resource group.
- The state resource group has a delete lock and the operator has Azure AD blob data access.
- The application resource group did not exist before apply, and the planned lake Storage and Key
  Vault names passed Azure name-availability checks immediately before apply review.
- The ignored `terraform/dev.tfvars` uses Central India, environment `dev`, a USD 10 alert budget,
  teardown date `2026-08-19`, and `enable_event_hubs=false`.

These bootstrap resources can incur small storage transaction/capacity charges. No application
resource group or Databricks compute has been created.

## Saved plan

- File: ignored local `terraform/stage-04.tfplan`.
- SHA-256: `947eaa823fc34f5c9b9a85dd68d6afe30e53311eee377e1054c1231f66157596`.
- Summary: 18 additions, 0 changes, 0 destroys.

| Count | Terraform resource type |
|---:|---|
| 1 | Subscription budget |
| 1 | Resource group |
| 1 | ADLS-enabled storage account |
| 1 | ADLS filesystem |
| 6 | ADLS directories |
| 1 | Data Factory with system identity |
| 1 | Premium Databricks workspace, no compute |
| 1 | Databricks Access Connector with system identity |
| 1 | Key Vault |
| 4 | Filesystem/Key Vault role assignments |

## Cost and safety review

The Terraform plan contained no Event Hubs namespace or hubs, Databricks cluster, SQL warehouse,
VM, explicit NAT gateway, Log Analytics workspace, ADF pipeline run, or trigger. Event Hubs output
was empty.

## Post-apply result

- Apply completed with 18 additions, 0 changes, and 0 destroys.
- A subsequent Terraform plan reported no drift.
- Event Hubs, Databricks compute, and ADF triggers remain absent.
- The subscription budget is USD 10; it alerts but does not cap spending.
- Both workload identities have filesystem-scoped lake access and ADF has Key Vault secret access.
- All six lake directories exist.
- Azure Databricks created a NAT gateway and Standard public IP in its locked managed resource
  group even though neither appeared as an explicit Terraform plan resource. Microsoft documents
  this as the expected behavior for secure cluster connectivity with a managed VNet and notes the
  additional cost.

The earlier statement that the plan had no NAT gateway was true only of the explicit Terraform
resource list and was not a sufficient post-deployment cost assertion. The parked minimal-cost
baseline now excludes the Databricks workspace; the workspace is enabled only for bounded demo
sessions.

Public service endpoints remain enabled for this short portfolio demonstration. Storage shared-key
authentication remains available for the initial Terraform data-plane provisioning; workload code
uses managed identities and no account key is exposed as an output. Hardening shared-key access is
a post-bootstrap follow-up after Azure AD data-plane provisioning is proven.

The saved plan was consumed by the successful apply. Any subsequent change requires a new saved
plan and review; do not reuse the old plan file.

## Pending cost-pause plan

A separate ignored plan, `terraform/stage-04-park-databricks.tfplan`, was refreshed after the
Stage 4 role correction. Its SHA-256 is
`789ddcf9cf0f62f08bb5f09495a71347bb10e45bfd2b1232cb9b2ba4fd99b982`.

The plan is 0 additions, 0 changes, and 1 destroy: only the Databricks workspace. Its workspace URL
output becomes null. It does not destroy the project resource group, ADLS, lake directories, ADF,
Key Vault, Access Connector, role assignments, budget, or remote-state resources. This plan is
prepared but must not be applied without an explicit cost-pause decision.

Operator decision on 2026-08-12: do not apply this plan yet. Keep the workspace available for the
seven-day build because the subscription has USD 200 of free credit, while keeping Event Hubs and
all Databricks compute disabled. At August 2026 retail rates, the managed NAT gateway and Standard
static IPv4 are estimated at approximately USD 0.05/hour combined, or USD 8.40 over seven full
days, excluding data processing, storage, transactions, and compute. Review Azure Cost Analysis
daily and apply the saved cost-pause plan early if usage deviates materially from that estimate.
