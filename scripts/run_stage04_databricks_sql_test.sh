#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
az_cli="${project_root}/scripts/azure_cli.sh"
databricks_resource="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"

: "${RETAILPULSE_DATABRICKS_HOST:?Set RETAILPULSE_DATABRICKS_HOST without an https:// prefix.}"
: "${RETAILPULSE_DATABRICKS_WAREHOUSE_ID:?Set RETAILPULSE_DATABRICKS_WAREHOUSE_ID.}"
: "${RETAILPULSE_DATABRICKS_CATALOG:?Set RETAILPULSE_DATABRICKS_CATALOG.}"
: "${RETAILPULSE_LAKE_ABFSS:?Set RETAILPULSE_LAKE_ABFSS to the filesystem URL.}"

if [[ ! "${RETAILPULSE_DATABRICKS_HOST}" =~ ^adb-[0-9]+\.[0-9]+\.azuredatabricks\.net$ ]]; then
  echo "RETAILPULSE_DATABRICKS_HOST is not a workspace hostname." >&2
  exit 2
fi
if [[ ! "${RETAILPULSE_DATABRICKS_WAREHOUSE_ID}" =~ ^[a-zA-Z0-9]+$ ]]; then
  echo "RETAILPULSE_DATABRICKS_WAREHOUSE_ID contains unsupported characters." >&2
  exit 2
fi
if [[ ! "${RETAILPULSE_DATABRICKS_CATALOG}" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "RETAILPULSE_DATABRICKS_CATALOG contains unsupported characters." >&2
  exit 2
fi
if [[ ! "${RETAILPULSE_LAKE_ABFSS}" =~ ^abfss://retailpulse@[a-z0-9]+\.dfs\.core\.windows\.net/?$ ]]; then
  echo "RETAILPULSE_LAKE_ABFSS is not the RetailPulse filesystem URL." >&2
  exit 2
fi

workspace_url="https://${RETAILPULSE_DATABRICKS_HOST}"
schema_name="retailpulse_stage04"
table_name="adls_access_verification"
verification_id="stage-04-azure-20260812"
table_path="${RETAILPULSE_LAKE_ABFSS%/}/silver/_access_tests/stage-04-databricks/delta_table"

stop_warehouse() {
  "${az_cli}" rest \
    --method post \
    --url "${workspace_url}/api/2.0/sql/warehouses/${RETAILPULSE_DATABRICKS_WAREHOUSE_ID}/stop" \
    --resource "${databricks_resource}" \
    --only-show-errors \
    --output none || true
}
trap stop_warehouse EXIT

run_sql() {
  local statement="$1"
  local schema="$2"
  local payload response state statement_id error_message

  payload="$(
    jq -cn \
      --arg warehouse_id "${RETAILPULSE_DATABRICKS_WAREHOUSE_ID}" \
      --arg catalog "${RETAILPULSE_DATABRICKS_CATALOG}" \
      --arg schema "${schema}" \
      --arg statement "${statement}" \
      '{
        warehouse_id: $warehouse_id,
        catalog: $catalog,
        schema: $schema,
        statement: $statement,
        wait_timeout: "50s",
        on_wait_timeout: "CONTINUE",
        disposition: "INLINE",
        format: "JSON_ARRAY"
      }'
  )"

  response="$(
    "${az_cli}" rest \
      --method post \
      --url "${workspace_url}/api/2.0/sql/statements" \
      --resource "${databricks_resource}" \
      --headers Content-Type=application/json \
      --body "${payload}" \
      --only-show-errors \
      --output json
  )"

  statement_id="$(jq -r '.statement_id' <<<"${response}")"
  for _ in $(seq 1 60); do
    state="$(jq -r '.status.state' <<<"${response}")"
    case "${state}" in
      SUCCEEDED)
        printf '%s\n' "${response}"
        return 0
        ;;
      FAILED|CANCELED|CLOSED)
        error_message="$(jq -r '.status.error.message // "No Databricks error message returned."' <<<"${response}")"
        echo "Databricks SQL statement ${state}: ${error_message}" >&2
        return 1
        ;;
    esac

    sleep 5
    response="$(
      "${az_cli}" rest \
        --method get \
        --url "${workspace_url}/api/2.0/sql/statements/${statement_id}" \
        --resource "${databricks_resource}" \
        --only-show-errors \
        --output json
    )"
  done

  echo "Databricks SQL statement timed out while waiting for completion." >&2
  return 1
}

run_sql "CREATE SCHEMA IF NOT EXISTS ${schema_name}" default >/dev/null

run_sql "CREATE TABLE IF NOT EXISTS ${table_name} (verification_id STRING, verified_at TIMESTAMP) USING DELTA LOCATION '${table_path}'" "${schema_name}" >/dev/null

run_sql "MERGE INTO ${table_name} AS target USING (SELECT '${verification_id}' AS verification_id, current_timestamp() AS verified_at) AS source ON target.verification_id = source.verification_id WHEN MATCHED THEN UPDATE SET verified_at = source.verified_at WHEN NOT MATCHED THEN INSERT (verification_id, verified_at) VALUES (source.verification_id, source.verified_at)" "${schema_name}" >/dev/null

result="$(run_sql "SELECT COUNT(*) AS matching_rows FROM ${table_name} WHERE verification_id = '${verification_id}'" "${schema_name}")"
matching_rows="$(jq -r '.result.data_array[0][0] // empty' <<<"${result}")"

if [[ "${matching_rows}" != "1" ]]; then
  echo "Databricks Delta verification expected one row, received '${matching_rows}'." >&2
  exit 1
fi

echo "STAGE4_DATABRICKS_ADLS_OK verification_id=${verification_id} matching_rows=${matching_rows}"
