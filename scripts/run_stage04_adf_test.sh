#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
az_cli="${project_root}/scripts/azure_cli.sh"
resource_group="${AZURE_RESOURCE_GROUP:-rg-retailpulse-dev-rp999}"
factory_name="${AZURE_DATA_FACTORY:-adf-retailpulse-dev-rp999}"
storage_account="${AZURE_STORAGE_ACCOUNT:-stretailpulsedevrp999}"
asset_root="azure/adf/stage04"

if [[ ! "${storage_account}" =~ ^[a-z0-9]{3,24}$ ]]; then
  echo "AZURE_STORAGE_ACCOUNT must be a valid lowercase storage-account name." >&2
  exit 2
fi

adls_properties="$(
  sed "s/STORAGE_ACCOUNT_NAME/${storage_account}/g" \
    "${project_root}/${asset_root}/ls_adls_managed_identity.json"
)"

"${az_cli}" datafactory linked-service create \
  --resource-group "${resource_group}" \
  --factory-name "${factory_name}" \
  --name ls_github_http \
  --properties "@${asset_root}/ls_github_http.json" \
  --only-show-errors \
  --output none

"${az_cli}" datafactory linked-service create \
  --resource-group "${resource_group}" \
  --factory-name "${factory_name}" \
  --name ls_adls_managed_identity \
  --properties "${adls_properties}" \
  --only-show-errors \
  --output none

"${az_cli}" datafactory dataset create \
  --resource-group "${resource_group}" \
  --factory-name "${factory_name}" \
  --name ds_github_readme_binary \
  --properties "@${asset_root}/ds_github_readme_binary.json" \
  --only-show-errors \
  --output none

"${az_cli}" datafactory dataset create \
  --resource-group "${resource_group}" \
  --factory-name "${factory_name}" \
  --name ds_adls_access_test_binary \
  --properties "@${asset_root}/ds_adls_access_test_binary.json" \
  --only-show-errors \
  --output none

"${az_cli}" datafactory pipeline create \
  --resource-group "${resource_group}" \
  --factory-name "${factory_name}" \
  --name pl_verify_adls_identity \
  --pipeline "@${asset_root}/pl_verify_adls_identity.json" \
  --only-show-errors \
  --output none

run_id="$(
  "${az_cli}" datafactory pipeline create-run \
    --resource-group "${resource_group}" \
    --factory-name "${factory_name}" \
    --name pl_verify_adls_identity \
    --query runId \
    --output tsv
)"

for _ in $(seq 1 60); do
  status="$(
    "${az_cli}" datafactory pipeline-run show \
      --resource-group "${resource_group}" \
      --factory-name "${factory_name}" \
      --run-id "${run_id}" \
      --query status \
      --output tsv
  )"

  case "${status}" in
    Succeeded)
      echo "STAGE4_ADF_ACCESS_OK run_id=${run_id}"
      exit 0
      ;;
    Failed|Cancelled)
      echo "Stage 4 ADF access test ended with status ${status}." >&2
      exit 1
      ;;
  esac

  sleep 5
done

echo "Stage 4 ADF access test timed out while waiting for completion." >&2
exit 1
