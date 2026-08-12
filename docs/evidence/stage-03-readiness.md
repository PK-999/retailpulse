# Stage 3 Azure deployment readiness

Verification date: 2026-08-12

## Pre-deployment account audit snapshot

- Azure CLI 2.88.0 authenticated through device code in an ignored local `.azure/` directory.
- Selected subscription alias: `Azure subscription 1`; state: enabled.
- Selected tenant alias: `Default Directory`.
- Operator authorization: subscription-level Owner.
- Existing resource groups: none.
- Existing subscription budgets: none.
- Central India is available and all five target service resource types advertise the region.
- At the time of the snapshot, only `Microsoft.Consumption` was registered. The required Storage,
  Event Hubs, Data Factory, Databricks, and Key Vault providers were registered before apply.

## Configuration improvements

- Terraform is pinned to 1.15.8 and AzureRM to 5.0.1.
- Provider auto-registration is disabled; only six documented providers will be registered.
- The random suffix was replaced with reviewed suffix `rp999`, making plan names deterministic.
- Azure Storage remote state, Azure AD data-plane access, and a delete-lock bootstrap are defined.
- The initially selected USD 100 subscription budget was reduced to USD 10 during Stage 4, before
  any apply. Its three Owner notifications cover state and managed resource groups too.
- Event Hubs and Storage enforce TLS 1.2; public blob nesting is disabled.
- Databricks compute remains outside Terraform, and Event Hubs defaults off, preventing compute and
  idle streaming charges during the base deployment.

## Name checks

- `kv-retailpulse-dev-rp999`: available.
- `evhns-retailpulse-dev-rp999`: available.
- Lake and state storage checks require `Microsoft.Storage` registration and will be repeated after
  the explicit registration step.
- The subscription currently contains no resource groups, eliminating in-subscription collisions
  for resource-group-scoped names.

## Pre-deployment gate (closed)

Before deployment, configuration validation passed and the following gate was used:

1. approve registration of the six required resource providers;
2. approve creation of the small remote-state resource group/storage/container and its role/lock;
3. initialize the backend and generate a saved plan;
4. review names, resource count, SKUs, and cost implications before any application deployment;
5. confirm the saved plan contains no Event Hubs namespace and no Databricks compute.

## Post-deployment update

The gate above was completed on 2026-08-12. The backend was initialized, the reviewed 18-add plan
was applied, and the later least-privilege Unity Catalog correction added one Storage Blob
Delegator assignment. The final Terraform plan reports no changes. Event Hubs and classic clusters
remain absent; the platform-created starter SQL warehouse is stopped with zero active clusters.

Azure Databricks created documented managed-VNet NAT networking that was not enumerated in the
Terraform plan. Its cost was reviewed and accepted as a time-bounded use of free credit through
the tagged teardown date. The Cost Management REST query returned HTTP 429 during final evidence
capture, so current actuals should be refreshed later in the Azure portal; this does not affect the
resource-health or identity gates.

## Closure recheck

On 2026-08-12, immediately before Stage 4 closure:

- a fresh Terraform refresh plan returned `No changes`;
- the monthly subscription budget was present at USD 10;
- the project resource group contained only the storage account, ADF, Key Vault, Databricks
  workspace, and Databricks Access Connector managed by this stage;
- the Event Hubs namespace list was empty;
- the only SQL warehouse was the platform-created starter warehouse in `STOPPED` state; and
- the classic cluster list was empty.
