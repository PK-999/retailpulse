# Stage 4 identity and storage verification runbook

Run this only after the reviewed Stage 3/4 Terraform plan has been applied.

## Cost gate: workspace lifecycle

The Databricks managed VNet includes a billable NAT gateway and public IP even with no compute.
Keep `enable_databricks_workspace=true` only while completing the Unity Catalog and Databricks
checks below. When pausing work, set it to `false`, create a fresh saved plan, confirm that only the
Databricks workspace will be destroyed, and apply that saved plan. The ADLS account, directories,
ADF, Key Vault, roles, Access Connector, budget, and remote state must remain.

Do not delete the NAT gateway or public IP directly from the locked Databricks-managed resource
group. They are removed with the workspace.

## 1. Inspect non-secret outputs

```bash
./scripts/terraform_azure.sh output
./scripts/terraform_azure.sh state list
```

Confirm the Access Connector and six directory resources exist. Do not copy tokens, connection
strings, or Terraform state into evidence.

## 2. Verify Azure role assignments

In the Azure portal, open the `retailpulse` filesystem and inspect **Access Control (IAM)**. Confirm
the ADF and Access Connector principal IDs match the Terraform outputs and both have Storage Blob
Data Contributor at the filesystem scope. Confirm the Access Connector also has Storage Blob
Delegator at the storage-account scope, which Unity Catalog requires to request short-lived user
delegation keys. On Key Vault IAM, confirm ADF is Secrets User and the deployment identity is
Secrets Officer.

Allow for Entra/RBAC propagation before diagnosing a recently created role assignment as broken.

## 3. Configure Unity Catalog

1. Confirm the workspace is attached to a Unity Catalog metastore.
2. Copy `databricks/storage-credential.example.json` outside the repository and replace only the
   Access Connector resource ID from Terraform output.
3. Create the storage credential with an authenticated Databricks CLI profile.
4. Run `databricks/external-location.example.sql` after replacing the storage account placeholder.
5. Grant workload users permissions on the external location, not on the underlying credential.

The credential should be bound to the RetailPulse workspace if other workspaces share the
metastore.

The live dev environment now has credential and external location `retailpulse_dev_lake`. Rerun
the API list checks before attempting creation; the create endpoints are not update operations.

## 4. Positive tests

- ADF: configure managed-identity authentication in the ADLS linked service, write one harmless
  file beneath `landing/_access_tests/<verification_id>/`, then read its metadata.
- Databricks: run `databricks/verify_adls_access.py` as a bounded job and retain its
  `STAGE4_ADLS_ACCESS_OK` line plus Delta history.

For the current dev environment, `scripts/run_stage04_adf_test.sh` provides the reproducible ADF
test and `scripts/run_stage04_databricks_sql_test.sh` provides an equivalent bounded SQL warehouse
Delta proof. The SQL helper always requests a warehouse stop on exit.

## 5. Negative test

Select an Entra user or service principal with no lake RBAC and no Unity Catalog grant. Record its
object ID alias—not credentials—and show that listing the test path returns authorization denied.
Do not remove access from the deployment operator or production identities to simulate failure.

## 6. Secret handling

Event Hubs remains disabled until Stage 7. When its short-lived SAS credential exists, place its
value in a permission-restricted file outside the repository and run:

```bash
./scripts/set_eventhubs_secret.sh kv-retailpulse-dev-rp999 /private/tmp/eventhubs-secret.txt
```

Delete the local value file after confirming the Key Vault secret metadata. Never capture the
secret value in screenshots or command output.
