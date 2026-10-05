#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${RETAILPULSE_PYTHON_BIN:-${project_root}/.venv/bin/python}"
databricks_resource="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
databricks_host="${RETAILPULSE_DATABRICKS_HOST:-adb-7405605234206971.11.azuredatabricks.net}"
warehouse_id="${RETAILPULSE_DATABRICKS_WAREHOUSE_ID:-74d4ebde2c184d68}"
warehouse_start_timeout="${RETAILPULSE_WAREHOUSE_START_TIMEOUT_SECONDS:-600}"
warehouse_stop_timeout="${RETAILPULSE_WAREHOUSE_STOP_TIMEOUT_SECONDS:-180}"
workspace_url="https://${databricks_host}"

if [[ ! -x "${python_bin}" ]]; then
  echo "Python environment is missing at ${python_bin}; install the databricks extra." >&2
  exit 2
fi
if [[ ! "${databricks_host}" =~ ^adb-[0-9]+\.[0-9]+\.azuredatabricks\.net$ ]]; then
  echo "The Databricks hostname is invalid." >&2
  exit 2
fi
if [[ ! "${warehouse_id}" =~ ^[A-Za-z0-9]+$ ]]; then
  echo "The Databricks SQL warehouse ID is invalid." >&2
  exit 2
fi
if [[ ! "${warehouse_start_timeout}" =~ ^[0-9]+$ ]] || ((warehouse_start_timeout < 30)); then
  echo "RETAILPULSE_WAREHOUSE_START_TIMEOUT_SECONDS must be an integer of at least 30." >&2
  exit 2
fi
if [[ ! "${warehouse_stop_timeout}" =~ ^[0-9]+$ ]] || ((warehouse_stop_timeout < 30)); then
  echo "RETAILPULSE_WAREHOUSE_STOP_TIMEOUT_SECONDS must be an integer of at least 30." >&2
  exit 2
fi

if [[ -n "${DATABRICKS_TOKEN:-}" ]]; then
  echo "Using the Databricks token supplied in DATABRICKS_TOKEN."
else
  azure_config="${project_root}/.azure"
  if command -v az >/dev/null 2>&1 && AZURE_CONFIG_DIR="${azure_config}" az account show >/dev/null 2>&1; then
    azure_cli=(env "AZURE_CONFIG_DIR=${azure_config}" az)
  else
    azure_cli=("${project_root}/scripts/azure_cli.sh")
  fi

  export DATABRICKS_TOKEN="$(
    "${azure_cli[@]}" account get-access-token --resource "${databricks_resource}" \
      --query accessToken --output tsv --only-show-errors
  )"
  echo "Using a short-lived Microsoft Entra token from Azure CLI."
fi

databricks_api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local args=(
    --silent
    --show-error
    --fail-with-body
    --connect-timeout 10
    --max-time 30
    --request "${method}"
    --url "${workspace_url}${path}"
    --header "Authorization: Bearer ${DATABRICKS_TOKEN}"
    --header "Content-Type: application/json"
  )

  if [[ -n "${body}" ]]; then
    args+=(--data "${body}")
  fi
  curl "${args[@]}"
}

warehouse_state() {
  databricks_api GET "/api/2.0/sql/warehouses/${warehouse_id}" | jq -er '.state'
}

start_warehouse() {
  local state deadline
  deadline=$(($(date +%s) + warehouse_start_timeout))
  state="$(warehouse_state)"
  echo "SQL warehouse ${warehouse_id} initial state: ${state}."

  if [[ "${state}" == "STOPPING" ]]; then
    echo "Waiting for the SQL warehouse to finish stopping before restart."
    while [[ "${state}" == "STOPPING" ]]; do
      if (($(date +%s) >= deadline)); then
        echo "SQL warehouse did not reach RUNNING within ${warehouse_start_timeout}s; last state: ${state}." >&2
        return 1
      fi
      sleep 5
      state="$(warehouse_state)"
    done
  fi

  if [[ "${state}" == "STOPPED" ]]; then
    databricks_api POST "/api/2.0/sql/warehouses/${warehouse_id}/start" '{}' >/dev/null
    state="STARTING"
  fi

  while [[ "${state}" != "RUNNING" ]]; do
    if (($(date +%s) >= deadline)); then
      echo "SQL warehouse did not reach RUNNING within ${warehouse_start_timeout}s; last state: ${state}." >&2
      return 1
    fi
    case "${state}" in
      STARTING)
        sleep 5
        ;;
      *)
        echo "SQL warehouse cannot be started from state ${state}." >&2
        return 1
        ;;
    esac
    state="$(warehouse_state)"
  done
  echo "SQL warehouse ${warehouse_id} is RUNNING."
}

stop_warehouse() {
  local deadline attempt state accepted=0
  [[ -n "${DATABRICKS_TOKEN:-}" ]] || return 0
  deadline=$(($(date +%s) + warehouse_stop_timeout))
  for attempt in 1 2 3; do
    if databricks_api POST "/api/2.0/sql/warehouses/${warehouse_id}/stop" '{}' >/dev/null; then
      accepted=1
      break
    fi
    echo "WARNING: Warehouse stop request attempt ${attempt} failed." >&2
    if (($(date +%s) >= deadline)); then
      return 1
    fi
    sleep 5
  done
  ((accepted)) || return 1

  while true; do
    if state="$(warehouse_state)"; then
      if [[ "${state}" == "STOPPED" ]]; then
        echo "SQL warehouse ${warehouse_id} confirmed STOPPED."
        return 0
      fi
    else
      echo "WARNING: Could not read warehouse state during cleanup." >&2
    fi
    if (($(date +%s) >= deadline)); then
      echo "WARNING: Warehouse cleanup exceeded ${warehouse_stop_timeout}s; last state: ${state:-unavailable}." >&2
      return 1
    fi
    sleep 5
  done
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if ! stop_warehouse; then
    echo "WARNING: Cleanup could not confirm STOPPED for SQL warehouse ${warehouse_id}. Inspect it immediately; compute may still be running." >&2
    if ((exit_code == 0)); then
      exit_code=1
    fi
  fi
  unset DATABRICKS_TOKEN || true
  exit "${exit_code}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export RETAILPULSE_DATABRICKS_HOST="${databricks_host}"
export RETAILPULSE_DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/${warehouse_id}"

start_warehouse

"${python_bin}" "${project_root}/scripts/export_stage09_dashboard.py" \
  --output "${project_root}/bi-dashboard/public/data/dashboard.json"

npm --prefix "${project_root}/bi-dashboard" ci
npm --prefix "${project_root}/bi-dashboard" run lint
npm --prefix "${project_root}/bi-dashboard" run build

echo "Stage 9 snapshot reconciled and dashboard build completed."
