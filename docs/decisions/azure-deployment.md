# Azure deployment decision record

Decision date: 2026-08-12
Status: selected for the first `dev` demonstration; changes require a new reviewed plan

## Subscription and region

- Tenant alias: `Default Directory`.
- Subscription alias: `Azure subscription 1` (enabled and the only eligible subscription).
- Initial operator: the authenticated human user, with inherited subscription-level Owner role.
- Region: `centralindia`.
- Region verification: Storage Accounts, Event Hubs namespaces, Data Factory factories,
  Databricks workspaces, and Key Vault vaults all advertise Central India in this subscription.

Subscription and tenant IDs are deployment inputs, not documentation values. They stay in ignored
local Azure/Terraform files and remote state.

## Naming and environment

- Project: `retailpulse`.
- Environment: `dev`.
- Reviewed global suffix: `rp999`.
- Primary resource group: `rg-retailpulse-dev-rp999`.
- Databricks managed resource group: `rg-dbw-retailpulse-dev-rp999`.
- Terraform state resource group: `rg-retailpulse-tfstate-rp999`.

The explicit suffix replaces apply-time randomness so every name is visible in the saved plan.

## Budget and cost policy

- Monthly subscription budget: USD 10, covering the application, state, and Databricks-managed
  resource groups.
- Notifications: actual spend above 50% and 80%, plus forecast spend above 100%.
- Recipients: identities holding the Owner role at the budget scope.
- Important: Azure budgets notify; they do not automatically stop resources or cap charges.
- Avoided baseline: Event Hubs Standard, one throughput unit, was approximately USD 0.12/hour in
  the Central India public retail-price query on the decision date, excluding ingress events.
- Event Hubs is default-off in Terraform. It is enabled immediately before the bounded Stage 7
  run and disabled immediately afterward.
- Databricks compute is not created by Stage 3 Terraform. Later job compute must auto-terminate and
  be stopped after each validation.
- Azure jobs use the `azure` profile, default to `AvailableNow`, and have a 30-minute maximum.
- The workspace uses the Premium tier because Unity Catalog requires it. Terraform still creates
  no compute; later job DBUs follow Premium pricing and the same bounded runtime rules.
- Day-to-day and performance work uses local Spark/Delta. Free Edition is optional for
  non-commercial experiments and is not accepted as Azure integration evidence.
- Literal zero-cost mode stops after local validation. Any real apply is treated as a minimal-cost,
  time-bounded deployment and is normally destroyed after evidence capture. The current workspace
  has an explicit free-credit exception through its tagged teardown date; see `docs/cost-strategy.md`.

## State and identity

- Terraform state: Azure Storage container `tfstate`, key `retailpulse-dev.tfstate`.
- State protection: private container, Azure AD authentication, operator data-plane role, and a
  resource-group delete lock.
- Application resource providers are explicitly registered; AzureRM automatic bulk registration
  is disabled.
- ADF uses its system-assigned managed identity.
- Databricks lake access uses a dedicated system-assigned Access Connector and Unity Catalog
  storage credential/external location.
- ADF and the Access Connector receive Storage Blob Data Contributor only at the RetailPulse
  filesystem scope. ADF additionally receives Key Vault Secrets User.
- Secret values are inserted after deployment and never managed by Terraform.
- GitHub deployments will use OIDC federation later; no long-lived Azure client secret will be
  stored in GitHub.

## Consumption and teardown

- First BI target: RetailPulse BI Lite, with Databricks SQL as the bounded query engine and a
  validated static snapshot published through GitHub Pages. See
  [the BI dashboard decision](bi-dashboard.md).
- Resource teardown date tag: `2026-08-19`.
- Stop all Databricks compute immediately after each test.
- Run `terraform destroy` after the final recorded demonstration unless further testing is
  explicitly scheduled.
- Retain the locked state account until destroy evidence and final outputs are archived, then
  remove its delete lock and delete it deliberately.
