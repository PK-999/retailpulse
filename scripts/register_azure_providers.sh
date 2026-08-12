#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
azure_cli="${project_root}/scripts/azure_cli.sh"

providers=(
  Microsoft.Consumption
  Microsoft.Databricks
  Microsoft.DataFactory
  Microsoft.EventHub
  Microsoft.KeyVault
  Microsoft.Storage
)

for provider in "${providers[@]}"; do
  echo "Registering ${provider}"
  "${azure_cli}" provider register --namespace "${provider}" --wait --output none
done

"${azure_cli}" provider list \
  --query "[?contains(['Microsoft.Consumption','Microsoft.Databricks','Microsoft.DataFactory','Microsoft.EventHub','Microsoft.KeyVault','Microsoft.Storage'], namespace)].{namespace:namespace,state:registrationState}" \
  --output table
