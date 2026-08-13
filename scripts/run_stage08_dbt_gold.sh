#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
az_cli="${project_root}/scripts/azure_cli.sh"
tf_cli="${project_root}/scripts/terraform_azure.sh"
dbt_bin="${RETAILPULSE_DBT_BIN:-${project_root}/.venv313/bin/dbt}"
databricks_resource="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
catalog_name="${RETAILPULSE_DBT_CATALOG:-dbw_retailpulse_dev_rp999}"
gold_schema="${RETAILPULSE_DBT_SCHEMA:-retailpulse_gold}"
source_schema="${RETAILPULSE_DBT_SOURCE_SCHEMA:-retailpulse_silver}"
job_name="retailpulse-stage08-dbt-gold"
repository_url="${RETAILPULSE_GIT_URL:-https://github.com/PK-999/retailpulse.git}"
git_branch="${RETAILPULSE_GIT_BRANCH:-$(git -C "${project_root}" branch --show-current)}"

databricks_host="${RETAILPULSE_DATABRICKS_HOST:-$("${tf_cli}" output -raw databricks_workspace_url)}"
lake_abfss="${RETAILPULSE_LAKE_ABFSS:-$("${tf_cli}" output -raw lake_abfss_url)}"
workspace_url="https://${databricks_host}"

if [[ ! -x "${dbt_bin}" ]]; then
  echo "dbt is missing at ${dbt_bin}; create a Python 3.11-3.13 environment with the analytics extra." >&2
  exit 2
fi
if [[ ! "${databricks_host}" =~ ^adb-[0-9]+\.[0-9]+\.azuredatabricks\.net$ ]]; then
  echo "The Terraform Databricks output is not a workspace hostname." >&2
  exit 2
fi
if [[ ! "${catalog_name}" =~ ^[A-Za-z0-9_]+$ ]] || [[ ! "${gold_schema}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "The dbt catalog and schema must contain only letters, numbers, and underscores." >&2
  exit 2
fi
if [[ ! "${lake_abfss}" =~ ^abfss://retailpulse@[a-z0-9]+\.dfs\.core\.windows\.net/?$ ]]; then
  echo "The Terraform lake output is not the RetailPulse filesystem URL." >&2
  exit 2
fi
if [[ -z "${git_branch}" ]]; then
  echo "Stage 8 scheduling requires a named Git branch." >&2
  exit 2
fi
lake_abfss="${lake_abfss%/}"

databricks_get() {
  local path="$1"
  "${az_cli}" rest --method get --url "${workspace_url}${path}" \
    --resource "${databricks_resource}" --only-show-errors --output json
}

databricks_post() {
  local path="$1"
  local body="$2"
  "${az_cli}" rest --method post --url "${workspace_url}${path}" \
    --resource "${databricks_resource}" --headers Content-Type=application/json \
    --body "${body}" --only-show-errors --output json
}

warehouses="$(databricks_get "/api/2.0/sql/warehouses")"
warehouse_id="${RETAILPULSE_DATABRICKS_WAREHOUSE_ID:-$(
  jq -r '.warehouses[]? | select(.enable_serverless_compute == true) | .id' \
    <<<"${warehouses}" | head -n 1
)}"
if [[ ! "${warehouse_id}" =~ ^[A-Za-z0-9]+$ ]]; then
  echo "No serverless SQL warehouse is available for the bounded Stage 8 build." >&2
  exit 2
fi

price_changed=false
scd_product_id=""
original_price=""

stop_warehouse() {
  databricks_post "/api/2.0/sql/warehouses/${warehouse_id}/stop" '{}' >/dev/null 2>&1 || true
}

cleanup() {
  if [[ "${price_changed}" == "true" ]] && [[ -n "${scd_product_id}" ]] && \
      [[ "${original_price}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    run_sql "UPDATE \`${catalog_name}\`.\`${source_schema}\`.\`products\` SET unit_price = CAST('${original_price}' AS DECIMAL(12,2)) WHERE product_id = '${scd_product_id}'" \
      "${source_schema}" >/dev/null 2>&1 || true
  fi
  unset DATABRICKS_TOKEN || true
  stop_warehouse
}
trap cleanup EXIT

run_sql() {
  local statement="$1"
  local schema="$2"
  local payload response state statement_id
  payload="$(
    jq -cn --arg warehouse_id "${warehouse_id}" --arg catalog "${catalog_name}" \
      --arg schema "${schema}" --arg statement "${statement}" \
      '{warehouse_id:$warehouse_id,catalog:$catalog,schema:$schema,statement:$statement,
        wait_timeout:"50s",on_wait_timeout:"CONTINUE",disposition:"INLINE",format:"JSON_ARRAY"}'
  )"
  response="$(databricks_post "/api/2.0/sql/statements" "${payload}")"
  statement_id="$(jq -r '.statement_id' <<<"${response}")"
  for _ in $(seq 1 120); do
    state="$(jq -r '.status.state' <<<"${response}")"
    case "${state}" in
      SUCCEEDED)
        printf '%s\n' "${response}"
        return 0
        ;;
      FAILED|CANCELED|CLOSED)
        echo "Databricks SQL ${state}: $(jq -r '.status.error.message // "unknown error"' <<<"${response}")" >&2
        return 1
        ;;
    esac
    sleep 5
    response="$(databricks_get "/api/2.0/sql/statements/${statement_id}")"
  done
  echo "Databricks SQL statement ${statement_id} timed out." >&2
  return 1
}

cell() {
  local response="$1"
  local column="$2"
  jq -r --arg column "${column}" '
    (.manifest.schema.columns | map(.name) | index($column)) as $index |
    .result.data_array[0][$index] // empty
  ' <<<"${response}"
}

export RETAILPULSE_DBT_TARGET="databricks"
export RETAILPULSE_DATABRICKS_HOST="${databricks_host}"
export RETAILPULSE_DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/${warehouse_id}"
export RETAILPULSE_DBT_CATALOG="${catalog_name}"
export RETAILPULSE_DBT_SOURCE_CATALOG="${catalog_name}"
export RETAILPULSE_DBT_SOURCE_SCHEMA="${source_schema}"
export RETAILPULSE_DBT_SCHEMA="${gold_schema}"
export RETAILPULSE_DBT_GOLD_LOCATION="${lake_abfss}/gold/dbt"
export DATABRICKS_TOKEN="$(
  "${az_cli}" account get-access-token --resource "${databricks_resource}" \
    --query accessToken --output tsv --only-show-errors
)"

source_gate="$(run_sql "
SELECT
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`customers\`) AS customers,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`products\`) AS products,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`orders\`) AS orders,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`order_items\`) AS order_items,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`streaming_events\`) AS streaming_events,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`retailpulse_ops\`.\`historical_batch_runs\` WHERE status = 'SUCCESS') AS successful_historical_runs,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`retailpulse_ops\`.\`streaming_batch_runs\`) AS streaming_batches
" "${source_schema}")"
for required in customers products orders order_items streaming_events streaming_batches; do
  if (( $(cell "${source_gate}" "${required}") < 1 )); then
    echo "Stage 8 Silver readiness failed for ${required}." >&2
    exit 1
  fi
done
if (( $(cell "${source_gate}" "successful_historical_runs") < 2 )); then
  echo "Stage 8 requires two successful Stage 6 historical runs." >&2
  exit 1
fi

dbt_args=(--project-dir "${project_root}/dbt" --profiles-dir "${project_root}/dbt" --target databricks)
"${dbt_bin}" debug "${dbt_args[@]}"
"${dbt_bin}" compile "${dbt_args[@]}"
"${dbt_bin}" build "${dbt_args[@]}"
"${dbt_bin}" build "${dbt_args[@]}"

reconciliation="$(run_sql "
SELECT
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`customers\`) AS silver_customers,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${gold_schema}\`.\`dim_customer\`) AS gold_customers,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`products\`) AS silver_products,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${gold_schema}\`.\`dim_product\`) AS gold_products,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${source_schema}\`.\`order_items\`) AS silver_items,
  (SELECT COUNT(*) FROM \`${catalog_name}\`.\`${gold_schema}\`.\`fact_order_items\`) AS gold_items,
  (SELECT ROUND(SUM(quantity * unit_price), 2) FROM \`${catalog_name}\`.\`${source_schema}\`.\`order_items\`) AS silver_revenue,
  (SELECT ROUND(SUM(line_total), 2) FROM \`${catalog_name}\`.\`${gold_schema}\`.\`fact_order_items\`) AS gold_revenue,
  (SELECT ROUND(SUM(revenue), 2) FROM \`${catalog_name}\`.\`${gold_schema}\`.\`daily_sales\`) AS daily_revenue
" "${gold_schema}")"
for pair in "silver_customers gold_customers" "silver_products gold_products" \
  "silver_items gold_items" "silver_revenue gold_revenue" "gold_revenue daily_revenue"; do
  read -r left right <<<"${pair}"
  if [[ "$(cell "${reconciliation}" "${left}")" != "$(cell "${reconciliation}" "${right}")" ]]; then
    echo "Stage 8 reconciliation failed: ${left} != ${right}." >&2
    exit 1
  fi
done

incremental_metrics='{}'
for model in fact_order_items fact_orders daily_sales; do
  history="$(run_sql "DESCRIBE HISTORY \`${catalog_name}\`.\`${gold_schema}\`.\`${model}\` LIMIT 1" "${gold_schema}")"
  operation="$(cell "${history}" "operation")"
  metrics="$(cell "${history}" "operationMetrics")"
  if [[ "${operation}" != "MERGE" ]] || [[ "$(jq -r '.numSourceRows // "missing"' <<<"${metrics}")" != "0" ]]; then
    echo "Second dbt build did not produce a zero-source incremental MERGE for ${model}." >&2
    exit 1
  fi
  incremental_metrics="$(jq -c --arg model "${model}" --argjson metrics "${metrics}" '. + {($model):$metrics}' <<<"${incremental_metrics}")"
done

product="$(run_sql "SELECT product_id, CAST(unit_price AS STRING) AS unit_price FROM \`${catalog_name}\`.\`${source_schema}\`.\`products\` ORDER BY product_id LIMIT 1" "${source_schema}")"
scd_product_id="$(cell "${product}" "product_id")"
original_price="$(cell "${product}" "unit_price")"
if [[ ! "${scd_product_id}" =~ ^[A-Za-z0-9_-]+$ ]] || [[ ! "${original_price}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "Unable to select a safe product for the SCD2 price-change proof." >&2
  exit 1
fi

price_changed=true
run_sql "UPDATE \`${catalog_name}\`.\`${source_schema}\`.\`products\` SET unit_price = unit_price + CAST('1.00' AS DECIMAL(12,2)) WHERE product_id = '${scd_product_id}'" "${source_schema}" >/dev/null
"${dbt_bin}" run "${dbt_args[@]}" --select dim_product
"${dbt_bin}" snapshot "${dbt_args[@]}"

scd_changed="$(run_sql "SELECT COUNT(*) AS versions, SUM(CASE WHEN dbt_valid_to IS NULL THEN 1 ELSE 0 END) AS current_versions FROM \`${catalog_name}\`.\`${gold_schema}\`.\`product_snapshot\` WHERE product_id = '${scd_product_id}'" "${gold_schema}")"
if (( $(cell "${scd_changed}" "versions") < 2 )) || [[ "$(cell "${scd_changed}" "current_versions")" != "1" ]]; then
  echo "The product price change did not create a valid second SCD2 version." >&2
  exit 1
fi

run_sql "UPDATE \`${catalog_name}\`.\`${source_schema}\`.\`products\` SET unit_price = CAST('${original_price}' AS DECIMAL(12,2)) WHERE product_id = '${scd_product_id}'" "${source_schema}" >/dev/null
price_changed=false
"${dbt_bin}" run "${dbt_args[@]}" --select dim_product
"${dbt_bin}" snapshot "${dbt_args[@]}"
"${dbt_bin}" test "${dbt_args[@]}"
"${dbt_bin}" docs generate "${dbt_args[@]}"

job_settings="$(
  jq -cn \
    --arg name "${job_name}" \
    --arg git_url "${repository_url}" \
    --arg git_branch "${git_branch}" \
    --arg warehouse_id "${warehouse_id}" \
    --arg catalog "${catalog_name}" \
    --arg schema "${gold_schema}" \
    '{
      name:$name,
      description:"Paused low-cost Stage 8 workflow: verified Silver gate, then tested dbt Gold.",
      max_concurrent_runs:1,
      timeout_seconds:1800,
      performance_target:"STANDARD",
      queue:{enabled:true},
      tags:{project:"retailpulse",environment:"dev",stage:"08",profile:"azure"},
      schedule:{quartz_cron_expression:"0 0 9 ? * MON",timezone_id:"Asia/Kolkata",pause_status:"PAUSED"},
      git_source:{git_url:$git_url,git_provider:"gitHub",git_branch:$git_branch},
      tasks:[
        {
          task_key:"silver_freshness_gate",
          notebook_task:{notebook_path:"databricks/verify_stage08_sources",source:"GIT",base_parameters:{catalog_name:$catalog}},
          environment_key:"serverless",
          timeout_seconds:900,
          max_retries:0
        },
        {
          task_key:"dbt_gold_build",
          depends_on:[{task_key:"silver_freshness_gate"}],
          dbt_task:{
            project_directory:"dbt",
            commands:["dbt build --target databricks_job"],
            warehouse_id:$warehouse_id,
            profiles_directory:"dbt",
            catalog:$catalog,
            schema:$schema
          },
          environment_key:"dbt",
          timeout_seconds:1800,
          max_retries:0
        }
      ],
      environments:[
        {environment_key:"serverless",spec:{environment_version:"4",dependencies:[]}},
        {environment_key:"dbt",spec:{environment_version:"4",dependencies:["dbt-databricks==1.9.8"]}}
      ]
    }'
)"
jobs="$(databricks_get "/api/2.2/jobs/list?name=${job_name}&limit=20")"
job_id="$(jq -r --arg name "${job_name}" '.jobs[]? | select(.settings.name == $name) | .job_id' <<<"${jobs}" | head -n 1)"
if [[ -n "${job_id}" ]]; then
  databricks_post "/api/2.2/jobs/reset" \
    "$(jq -cn --argjson job_id "${job_id}" --argjson settings "${job_settings}" '{job_id:$job_id,new_settings:$settings}')" >/dev/null
else
  job_id="$(databricks_post "/api/2.2/jobs/create" "${job_settings}" | jq -r '.job_id')"
fi

warehouse_state="$(databricks_get "/api/2.0/sql/warehouses/${warehouse_id}" | jq -r '.state')"
jq -cn \
  --arg status "STAGE8_DBT_GOLD_VERIFIED" \
  --arg warehouse_id "${warehouse_id}" \
  --arg warehouse_state_before_cleanup "${warehouse_state}" \
  --argjson job_id "${job_id}" \
  --arg git_branch "${git_branch}" \
  --arg scd_product_id "${scd_product_id}" \
  --argjson source_gate "$(jq -c '.result.data_array[0]' <<<"${source_gate}")" \
  --argjson reconciliation "$(jq -c '.result.data_array[0]' <<<"${reconciliation}")" \
  --argjson incremental_metrics "${incremental_metrics}" \
  --argjson scd_versions "$(cell "${scd_changed}" "versions")" \
  '{status:$status,warehouse_id:$warehouse_id,warehouse_state_before_cleanup:$warehouse_state_before_cleanup,
    scheduled_job:{job_id:$job_id,git_branch:$git_branch,pause_status:"PAUSED"},
    scd2:{product_id:$scd_product_id,changed_versions:$scd_versions,source_restored:true},
    source_gate:$source_gate,reconciliation:$reconciliation,incremental_metrics:$incremental_metrics}'
