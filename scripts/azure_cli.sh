#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${project_root}/.azure"

docker run --rm \
  --volume "${project_root}/.azure:/root/.azure" \
  mcr.microsoft.com/azure-cli:2.88.0-azurelinux3.0 \
  az "$@"
