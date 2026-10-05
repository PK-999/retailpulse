#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
az_cli="${project_root}/scripts/azure_cli.sh"
tf_cli="${project_root}/scripts/terraform_azure.sh"
databricks_resource="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
notebook_path="/Shared/retailpulse/stage06/batch_bronze_silver"
job_name="retailpulse-stage06-historical-batch"
catalog_name="${RETAILPULSE_DATABRICKS_CATALOG:-dbw_retailpulse_dev_rp999}"
first_delivery="${RETAILPULSE_STAGE6_FIRST_ADF_RUN_ID:-3d93e4ea-9630-11f1-8f9b-ce7c4dd55c3a}"
second_delivery="${RETAILPULSE_STAGE6_SECOND_ADF_RUN_ID:-80c5eb5c-9633-11f1-bfd1-bef4437dcc7c}"

databricks_host="${RETAILPULSE_DATABRICKS_HOST:-$("${tf_cli}" output -raw databricks_workspace_url)}"
lake_abfss="${RETAILPULSE_LAKE_ABFSS:-$("${tf_cli}" output -raw lake_abfss_url)}"
workspace_url="https://${databricks_host}"

if [[ ! "${databricks_host}" =~ ^adb-[0-9]+\.[0-9]+\.azuredatabricks\.net$ ]]; then
  echo "The Terraform Databricks output is not a workspace hostname." >&2
  exit 2
fi
if [[ ! "${lake_abfss}" =~ ^abfss://retailpulse@[a-z0-9]+\.dfs\.core\.windows\.net/?$ ]]; then
  echo "The Terraform lake output is not the RetailPulse filesystem URL." >&2
  exit 2
fi
if [[ ! "${catalog_name}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "RETAILPULSE_DATABRICKS_CATALOG contains unsupported characters." >&2
  exit 2
fi
for delivery in "${first_delivery}" "${second_delivery}"; do
  if [[ ! "${delivery}" =~ ^[a-f0-9-]{36}$ ]]; then
    echo "Stage 6 ADF run IDs must be UUIDs." >&2
    exit 2
  fi
done
if [[ "${first_delivery}" == "${second_delivery}" ]]; then
  echo "Stage 6 requires two different Stage 5 delivery IDs." >&2
  exit 2
fi
lake_abfss="${lake_abfss%/}"

databricks_get() {
  local path="$1"
  local attempt response
  for attempt in $(seq 1 8); do
    if response="$(
      "${az_cli}" rest --method get --url "${workspace_url}${path}" \
        --resource "${databricks_resource}" --only-show-errors --output json 2>&1
    )"; then
      printf '%s\n' "${response}"
      return 0
    fi
    sleep $((attempt * 3))
  done
  echo "Databricks GET failed after retries for ${path}: ${response}" >&2
  return 1
}

databricks_post() {
  local path="$1"
  local body="$2"
  local attempt response
  for attempt in $(seq 1 5); do
    if response="$(
      "${az_cli}" rest --method post --url "${workspace_url}${path}" \
        --resource "${databricks_resource}" --headers Content-Type=application/json \
        --body "${body}" --only-show-errors --output json 2>&1
    )"; then
      printf '%s\n' "${response}"
      return 0
    fi
    sleep $((attempt * 3))
  done
  echo "Databricks POST failed after retries for ${path}: ${response}" >&2
  return 1
}

deploy_job() {
  local content import_body settings jobs job_id response
  content="$(base64 < "${project_root}/databricks/batch_bronze_silver.py" | tr -d '\n')"
  databricks_post "/api/2.0/workspace/mkdirs" \
    "$(jq -cn --arg path "$(dirname "${notebook_path}")" '{path: $path}')" >/dev/null
  import_body="$(
    jq -cn --arg path "${notebook_path}" --arg content "${content}" \
      '{path:$path,format:"SOURCE",language:"PYTHON",overwrite:true,content:$content}'
  )"
  databricks_post "/api/2.0/workspace/import" "${import_body}" >/dev/null

  settings="$(
    jq -cn --arg name "${job_name}" --arg notebook_path "${notebook_path}" \
      '{
        name:$name,
        description:"Bounded Stage 6 historical Bronze/Silver/quality/audit proof.",
        max_concurrent_runs:1,
        timeout_seconds:1800,
        performance_target:"STANDARD",
        queue:{enabled:true},
        tags:{project:"retailpulse",environment:"dev",stage:"06",profile:"azure"},
        tasks:[{
          task_key:"historical_batch",
          notebook_task:{notebook_path:$notebook_path,source:"WORKSPACE"},
          environment_key:"serverless",
          timeout_seconds:1800,
          max_retries:0,
          retry_on_timeout:false,
          disable_auto_optimization:true
        }],
        environments:[{environment_key:"serverless",spec:{environment_version:"4",dependencies:[]}}]
      }'
  )"
  jobs="$(databricks_get "/api/2.2/jobs/list?name=${job_name}&limit=20")"
  job_id="$(jq -r --arg name "${job_name}" '.jobs[]? | select(.settings.name == $name) | .job_id' <<<"${jobs}" | head -n 1)"
  if [[ -n "${job_id}" ]]; then
    databricks_post "/api/2.2/jobs/reset" \
      "$(jq -cn --argjson job_id "${job_id}" --argjson settings "${settings}" \
        '{job_id:$job_id,new_settings:$settings}')" >/dev/null
  else
    response="$(databricks_post "/api/2.2/jobs/create" "${settings}")"
    job_id="$(jq -r '.job_id' <<<"${response}")"
  fi
  printf '%s\n' "${job_id}"
}

run_delivery() {
  local job_id="$1"
  local delivery_id="$2"
  local inject_invalid="$3"
  local landing_path body run_id state run result_state task_run_id output result
  landing_path="${lake_abfss}/landing/uci/normalized/${delivery_id}"
  body="$(
    jq -cn \
      --argjson job_id "${job_id}" \
      --arg landing_path "${landing_path}" \
      --arg base_path "${lake_abfss}" \
      --arg pipeline_run_id "${delivery_id}" \
      --arg catalog_name "${catalog_name}" \
      --arg inject_invalid_item "${inject_invalid}" \
      '{
        job_id:$job_id,
        notebook_params:{
          landing_path:$landing_path,
          base_path:$base_path,
          pipeline_run_id:$pipeline_run_id,
          catalog_name:$catalog_name,
          profile_name:"azure",
          max_customers:"1000",
          max_products:"250",
          max_orders:"5000",
          max_order_items:"25000",
          inject_invalid_item:$inject_invalid_item
        }
      }'
  )"
  run_id="$(databricks_post "/api/2.2/jobs/run-now" "${body}" | jq -r '.run_id')"
  echo "STAGE6_JOB_STARTED delivery=${delivery_id} job_run_id=${run_id} invalid=${inject_invalid}" >&2

  for _ in $(seq 1 180); do
    run="$(databricks_get "/api/2.2/jobs/runs/get?run_id=${run_id}")"
    state="$(jq -r '.state.life_cycle_state' <<<"${run}")"
    if [[ "${state}" == "TERMINATED" || "${state}" == "INTERNAL_ERROR" || "${state}" == "SKIPPED" ]]; then
      result_state="$(jq -r '.state.result_state // "UNKNOWN"' <<<"${run}")"
      if [[ "${result_state}" != "SUCCESS" ]]; then
        task_run_id="$(jq -r '.tasks[0].run_id // empty' <<<"${run}")"
        if [[ -n "${task_run_id}" ]]; then
          databricks_get "/api/2.2/jobs/runs/get-output?run_id=${task_run_id}" >&2 || true
        fi
        echo "STAGE6_JOB_FAILED delivery=${delivery_id} job_run_id=${run_id}" >&2
        return 1
      fi
      task_run_id="$(jq -r '.tasks[0].run_id' <<<"${run}")"
      output="$(databricks_get "/api/2.2/jobs/runs/get-output?run_id=${task_run_id}")"
      result="$(jq -r '.notebook_output.result' <<<"${output}")"
      jq -c --argjson job_id "${job_id}" --argjson job_run_id "${run_id}" \
        --argjson task_run_id "${task_run_id}" \
        --argjson setup_ms "$(jq '.tasks[0].setup_duration' <<<"${run}")" \
        --argjson execution_ms "$(jq '.tasks[0].execution_duration' <<<"${run}")" \
        '. + {job_id:$job_id,job_run_id:$job_run_id,task_run_id:$task_run_id,
          setup_duration_ms:$setup_ms,execution_duration_ms:$execution_ms}' <<<"${result}"
      return 0
    fi
    sleep 10
  done
  echo "STAGE6_JOB_TIMEOUT delivery=${delivery_id} job_run_id=${run_id}" >&2
  return 1
}

query_metrics() {
  local task_run_id="$1"
  local attempt history metrics
  for attempt in $(seq 1 12); do
    history="$(
      databricks_get "/api/2.0/sql/history/queries?include_metrics=true&max_results=999"
    )"
    metrics="$(
      jq -c --arg task_run_id "${task_run_id}" '
        [.res[] | select((.query_source.job_info.job_task_run_id | tostring) == $task_run_id)] as $queries |
        {
          statement_count: ($queries | length),
          failed_statement_count: ([$queries[] | select(.status == "FAILED")] | length),
          read_bytes: ([$queries[].metrics.read_bytes // 0] | add // 0),
          written_bytes: ([$queries[].metrics.write_remote_bytes // 0] | add // 0),
          written_rows: ([$queries[].metrics.write_remote_rows // 0] | add // 0),
          network_sent_bytes: ([$queries[].metrics.network_sent_bytes // 0] | add // 0),
          spill_to_disk_bytes: ([$queries[].metrics.spill_to_disk_bytes // 0] | add // 0),
          total_task_time_ms: ([$queries[].metrics.task_total_time_ms // 0] | add // 0)
        }' <<<"${history}"
    )"
    if (( $(jq -r '.statement_count' <<<"${metrics}") > 0 )); then
      printf '%s\n' "${metrics}"
      return 0
    fi
    sleep 10
  done
  echo "Query History did not publish metrics for task run ${task_run_id}." >&2
  return 1
}

job_id="$(deploy_job)"
echo "STAGE6_JOB_READY job_id=${job_id} performance_target=STANDARD schedule=none" >&2
first="$(run_delivery "${job_id}" "${first_delivery}" false)"
second="$(run_delivery "${job_id}" "${second_delivery}" true)"

first_metrics="$(query_metrics "$(jq -r '.task_run_id' <<<"${first}")")"
second_metrics="$(query_metrics "$(jq -r '.task_run_id' <<<"${second}")")"

if [[ "$(jq -r '.failed_statement_count' <<<"${first_metrics}")" != "0" ]] || \
   [[ "$(jq -r '.failed_statement_count' <<<"${second_metrics}")" != "0" ]]; then
  echo "Stage 6 Query History contains failed statements." >&2
  exit 1
fi

first_rejected="$(jq -r '.records_rejected' <<<"${first}")"
second_rejected="$(jq -r '.records_rejected' <<<"${second}")"
if (( second_rejected != first_rejected + 1 )); then
  echo "Second Stage 6 run did not add exactly one injected rejection to the source baseline." >&2
  exit 1
fi
if [[ "$(jq -r '.records_valid' <<<"${first}")" != \
      "$(jq -r '.records_valid' <<<"${second}")" ]]; then
  echo "The injected invalid row unexpectedly changed the valid-record count." >&2
  exit 1
fi
for dataset in customers products orders order_items; do
  first_total="$(jq -r --arg dataset "${dataset}" '.datasets[$dataset].silver_total' <<<"${first}")"
  second_total="$(jq -r --arg dataset "${dataset}" '.datasets[$dataset].silver_total' <<<"${second}")"
  if [[ "${first_total}" != "${second_total}" ]]; then
    echo "Silver ${dataset} changed across the identical valid delivery." >&2
    exit 1
  fi
done
if [[ "$(jq -r '.datasets.order_items.rejected_rows' <<<"${second}")" != \
      "$(( $(jq -r '.datasets.order_items.rejected_rows' <<<"${first}") + 1 ))" ]]; then
  echo "The injected rejection was not isolated to order_items." >&2
  exit 1
fi

jq -cn \
  --argjson job_id "${job_id}" \
  --argjson first "${first}" \
  --argjson second "${second}" \
  --argjson first_metrics "${first_metrics}" \
  --argjson second_metrics "${second_metrics}" \
  '{
    status:"STAGE6_HISTORICAL_BATCH_VERIFIED",
    job_id:$job_id,
    profile:"azure",
    first:($first + {query_metrics:$first_metrics}),
    second:($second + {query_metrics:$second_metrics})
  }'
