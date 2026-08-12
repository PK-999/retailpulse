# RetailPulse Azure access matrix

Last reviewed: 2026-08-12

No principal IDs or credentials are committed. Terraform resolves identities at deployment time.
The workspace uses the Premium tier because the selected Unity Catalog path requires it.

| Principal | Authentication | Azure scope | Role | Intended access |
|---|---|---|---|---|
| ADF factory | System-assigned managed identity | `retailpulse` filesystem | Storage Blob Data Contributor | Land historical files and read ingestion inputs |
| ADF factory | System-assigned managed identity | RetailPulse Key Vault | Key Vault Secrets User | Read explicitly referenced linked-service secrets |
| Databricks Access Connector | System-assigned managed identity | Storage account | Storage Blob Delegator | Request short-lived user delegation keys required by Unity Catalog |
| Databricks Access Connector | System-assigned managed identity | `retailpulse` filesystem | Storage Blob Data Contributor | Read/write only the governed RetailPulse lake paths through Unity Catalog |
| Terraform deployer | Existing Entra identity | RetailPulse Key Vault | Key Vault Secrets Officer | Create and rotate demo secrets; cannot manage vault RBAC through this role |

The filesystem role is intentionally scoped below the storage account. ADF still receives access
to all six paths in the shared filesystem because Azure RBAC does not provide directory-level role
assignment. If stronger separation becomes necessary, place Landing in a separate filesystem or
combine container RBAC with reviewed ADLS ACLs.

## Deliberately absent access

- No anonymous or public blob access.
- No storage account keys, SAS values, or Key Vault secret values in Terraform or Git.
- No Databricks personal access token in Terraform.
- No broad subscription-level data-plane role for either workload identity.
- No role is guessed for an unauthorized test principal; that principal is selected explicitly
  during external verification.
