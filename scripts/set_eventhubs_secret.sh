#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
azure_cli="${project_root}/scripts/azure_cli.sh"
secret_name="eventhubs-kafka-connection-string"

if [[ "$#" -ne 2 ]]; then
  echo "Usage: $0 <key-vault-name> <secret-file-outside-repository>" >&2
  exit 2
fi

vault_name="$1"
secret_file="$2"

if [[ ! -f "${secret_file}" ]]; then
  echo "Secret file does not exist: ${secret_file}" >&2
  exit 1
fi

secret_directory="$(cd "$(dirname "${secret_file}")" && pwd)"
secret_path="${secret_directory}/$(basename "${secret_file}")"
case "${secret_path}" in
  "${project_root}"/*)
    echo "Refusing to read a secret file from inside the repository." >&2
    exit 1
    ;;
esac

"${azure_cli}" keyvault secret set \
  --vault-name "${vault_name}" \
  --name "${secret_name}" \
  --file "${secret_path}" \
  --encoding utf-8 \
  --output none

echo "Stored ${secret_name} in ${vault_name}; no value was printed."
