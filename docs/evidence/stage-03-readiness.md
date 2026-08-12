# Stage 3 Azure deployment readiness

Verification date: 2026-08-12

## Read-only account audit

- Azure CLI 2.88.0 authenticated through device code in an ignored local `.azure/` directory.
- Selected subscription alias: `Azure subscription 1`; state: enabled.
- Selected tenant alias: `Default Directory`.
- Operator authorization: subscription-level Owner.
- Existing resource groups: none.
- Existing subscription budgets: none.
- Central India is available and all five target service resource types advertise the region.
- `Microsoft.Consumption` is registered. Storage, Event Hubs, Data Factory, Databricks, and Key
  Vault providers are not yet registered.

## Configuration improvements

- Terraform is pinned to 1.15.8 and AzureRM to 5.0.1.
- Provider auto-registration is disabled; only six documented providers will be registered.
- The random suffix was replaced with reviewed suffix `rp999`, making plan names deterministic.
- Azure Storage remote state, Azure AD data-plane access, and a delete-lock bootstrap are defined.
- A USD 100 subscription budget with three Owner notifications is defined so state and managed
  resource groups are covered too.
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

## Current gate

Configuration validation passes. No Azure resource has been created and no provider registration
has been changed. Before the saved plan can be produced:

1. approve registration of the six required resource providers;
2. approve creation of the small remote-state resource group/storage/container and its role/lock;
3. initialize the backend and generate a saved plan;
4. review names, resource count, SKUs, and cost implications before any application deployment;
5. confirm the saved plan contains no Event Hubs namespace and no Databricks compute.
