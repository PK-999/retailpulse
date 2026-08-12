#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
azure_cli="${project_root}/scripts/azure_cli.sh"

state_resource_group="${TF_STATE_RESOURCE_GROUP:-rg-retailpulse-tfstate-rp999}"
state_storage_account="${TF_STATE_STORAGE_ACCOUNT:-stretailpulsetfrp999}"
state_container="${TF_STATE_CONTAINER:-tfstate}"
location="${AZURE_LOCATION:-centralindia}"

if ! "${azure_cli}" group show --name "${state_resource_group}" --output none 2>/dev/null; then
  "${azure_cli}" group create \
    --name "${state_resource_group}" \
    --location "${location}" \
    --tags project=RetailPulse managed_by=bootstrap purpose=terraform-state \
    --output none
fi

if ! "${azure_cli}" storage account show \
  --resource-group "${state_resource_group}" \
  --name "${state_storage_account}" \
  --output none 2>/dev/null; then
  availability="$("${azure_cli}" storage account check-name \
    --name "${state_storage_account}" \
    --query nameAvailable \
    --output tsv)"
  if [[ "${availability}" != "true" ]]; then
    echo "Storage account name ${state_storage_account} is unavailable." >&2
    exit 1
  fi

  "${azure_cli}" storage account create \
    --resource-group "${state_resource_group}" \
    --name "${state_storage_account}" \
    --location "${location}" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --https-only true \
    --min-tls-version TLS1_2 \
    --allow-blob-public-access false \
    --tags project=RetailPulse managed_by=bootstrap purpose=terraform-state \
    --output none
fi

if ! "${azure_cli}" storage container-rm show \
  --storage-account "${state_storage_account}" \
  --name "${state_container}" \
  --output none 2>/dev/null; then
  "${azure_cli}" storage container-rm create \
    --storage-account "${state_storage_account}" \
    --name "${state_container}" \
    --public-access off \
    --output none
fi

storage_id="$("${azure_cli}" storage account show \
  --resource-group "${state_resource_group}" \
  --name "${state_storage_account}" \
  --query id \
  --output tsv)"
operator_id="$("${azure_cli}" ad signed-in-user show --query id --output tsv)"

if [[ "$("${azure_cli}" role assignment list \
  --assignee "${operator_id}" \
  --scope "${storage_id}" \
  --role "Storage Blob Data Owner" \
  --query 'length(@)' \
  --output tsv)" == "0" ]]; then
  "${azure_cli}" role assignment create \
    --assignee-object-id "${operator_id}" \
    --assignee-principal-type User \
    --scope "${storage_id}" \
    --role "Storage Blob Data Owner" \
    --output none
fi

if ! "${azure_cli}" lock show \
  --name retailpulse-tfstate-delete-lock \
  --resource-group "${state_resource_group}" \
  --output none 2>/dev/null; then
  "${azure_cli}" lock create \
    --name retailpulse-tfstate-delete-lock \
    --resource-group "${state_resource_group}" \
    --lock-type CanNotDelete \
    --notes "Protect RetailPulse Terraform state from accidental deletion." \
    --output none
fi

echo "Terraform state backend is ready: ${state_resource_group}/${state_storage_account}/${state_container}"
