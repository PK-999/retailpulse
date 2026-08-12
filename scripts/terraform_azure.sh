#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${project_root}/.azure"

docker run --rm \
  --volume "${project_root}:/work" \
  --volume "${project_root}/.azure:/root/.azure" \
  --workdir /work/terraform \
  retailpulse-azure-tools:1.15.8 \
  terraform "$@"
