#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
az_cli="${project_root}/scripts/azure_cli.sh"
tf_cli="${project_root}/scripts/terraform_azure.sh"
resource_group="${AZURE_RESOURCE_GROUP:-rg-retailpulse-dev-rp999}"
factory_name="${AZURE_DATA_FACTORY:-adf-retailpulse-dev-rp999}"
storage_account="${AZURE_STORAGE_ACCOUNT:-stretailpulsedevrp999}"
asset_root="azure/adf/stage05"
databricks_resource="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
notebook_path="/Shared/retailpulse/stage05/preprocess_uci"
job_name="retailpulse-stage05-normalize-uci"
source_base_url="${RETAILPULSE_UCI_BASE_URL:-https://archive.ics.uci.edu/}"
source_relative_url="${RETAILPULSE_UCI_RELATIVE_URL:-static/public/352/online+retail.zip}"
source_file_name="${RETAILPULSE_UCI_FILE_NAME:-online-retail.zip}"
expected_sha256="${RETAILPULSE_UCI_SHA256:-f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b}"
expected_size_bytes="${RETAILPULSE_UCI_SIZE_BYTES:-23715478}"
resume_adf_run_id="${RETAILPULSE_STAGE5_RESUME_ADF_RUN_ID:-}"
verify_existing_only="${RETAILPULSE_STAGE5_VERIFY_EXISTING_ONLY:-false}"

if [[ ! "${storage_account}" =~ ^[a-z0-9]{3,24}$ ]]; then
  echo "AZURE_STORAGE_ACCOUNT must be a valid lowercase storage-account name." >&2
  exit 2
fi
if [[ ! "${expected_sha256}" =~ ^[a-f0-9]{64}$ ]]; then
  echo "RETAILPULSE_UCI_SHA256 must be a lowercase SHA-256 digest." >&2
  exit 2
fi
if [[ ! "${expected_size_bytes}" =~ ^[1-9][0-9]*$ ]]; then
  echo "RETAILPULSE_UCI_SIZE_BYTES must be a positive integer." >&2
  exit 2
fi

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
lake_abfss="${lake_abfss%/}"

databricks_get() {
  local path="$1"
  local attempt response
  for attempt in $(seq 1 8); do
    if response="$(
      "${az_cli}" rest \
        --method get \
        --url "${workspace_url}${path}" \
        --resource "${databricks_resource}" \
        --only-show-errors \
        --output json 2>&1
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
      "${az_cli}" rest \
        --method post \
        --url "${workspace_url}${path}" \
        --resource "${databricks_resource}" \
        --headers Content-Type=application/json \
        --body "${body}" \
        --only-show-errors \
        --output json 2>&1
    )"; then
      printf '%s\n' "${response}"
      return 0
    fi
    sleep $((attempt * 3))
  done
  echo "Databricks POST failed after retries for ${path}: ${response}" >&2
  return 1
}

deploy_adf_assets() {
  local adls_properties
  adls_properties="$(
    sed "s/STORAGE_ACCOUNT_NAME/${storage_account}/g" \
      "${project_root}/azure/adf/stage04/ls_adls_managed_identity.json"
  )"

  "${az_cli}" datafactory linked-service create \
    --resource-group "${resource_group}" \
    --factory-name "${factory_name}" \
    --name ls_adls_managed_identity \
    --properties "${adls_properties}" \
    --only-show-errors \
    --output none

  "${az_cli}" datafactory linked-service create \
    --resource-group "${resource_group}" \
    --factory-name "${factory_name}" \
    --name ls_uci_http_parameterized \
    --properties "@${asset_root}/ls_uci_http_parameterized.json" \
    --only-show-errors \
    --output none

  "${az_cli}" datafactory dataset create \
    --resource-group "${resource_group}" \
    --factory-name "${factory_name}" \
    --name ds_uci_http_archive \
    --properties "@${asset_root}/ds_uci_http_archive.json" \
    --only-show-errors \
    --output none

  "${az_cli}" datafactory dataset create \
    --resource-group "${resource_group}" \
    --factory-name "${factory_name}" \
    --name ds_adls_uci_raw_archive \
    --properties "@${asset_root}/ds_adls_uci_raw_archive.json" \
    --only-show-errors \
    --output none

  "${az_cli}" datafactory pipeline create \
    --resource-group "${resource_group}" \
    --factory-name "${factory_name}" \
    --name pl_ingest_uci_to_adls \
    --pipeline "@${asset_root}/pl_ingest_uci_to_adls.json" \
    --only-show-errors \
    --output none
}

deploy_databricks_job() {
  local notebook_content import_body settings jobs job_id response
  notebook_content="$(base64 < "${project_root}/databricks/preprocess_uci.py" | tr -d '\n')"

  databricks_post "/api/2.0/workspace/mkdirs" \
    "$(jq -cn --arg path "$(dirname "${notebook_path}")" '{path: $path}')" >/dev/null
  import_body="$(
    jq -cn \
      --arg path "${notebook_path}" \
      --arg content "${notebook_content}" \
      '{path: $path, format: "SOURCE", language: "PYTHON", overwrite: true, content: $content}'
  )"
  databricks_post "/api/2.0/workspace/import" "${import_body}" >/dev/null

  settings="$(
    jq -cn \
      --arg name "${job_name}" \
      --arg notebook_path "${notebook_path}" \
      '{
        name: $name,
        description: "Bounded Stage 5 normalization of one immutable UCI ADF delivery.",
        max_concurrent_runs: 1,
        timeout_seconds: 1800,
        performance_target: "STANDARD",
        queue: {enabled: true},
        tags: {project: "retailpulse", environment: "dev", stage: "05"},
        tasks: [
          {
            task_key: "normalize_uci",
            description: "Validate the UCI archive and create four run-scoped JSONL datasets.",
            notebook_task: {notebook_path: $notebook_path, source: "WORKSPACE"},
            environment_key: "serverless",
            timeout_seconds: 1800,
            max_retries: 0,
            retry_on_timeout: false,
            disable_auto_optimization: true
          }
        ],
        environments: [
          {
            environment_key: "serverless",
            spec: {environment_version: "4", dependencies: ["openpyxl==3.1.5"]}
          }
        ]
      }'
  )"

  jobs="$(databricks_get "/api/2.2/jobs/list?name=${job_name}&limit=20")"
  job_id="$(jq -r --arg name "${job_name}" '.jobs[]? | select(.settings.name == $name) | .job_id' <<<"${jobs}" | head -n 1)"
  if [[ -n "${job_id}" ]]; then
    databricks_post "/api/2.2/jobs/reset" \
      "$(jq -cn --argjson job_id "${job_id}" --argjson settings "${settings}" '{job_id: $job_id, new_settings: $settings}')" \
      >/dev/null
  else
    response="$(databricks_post "/api/2.2/jobs/create" "${settings}")"
    job_id="$(jq -r '.job_id' <<<"${response}")"
  fi
  printf '%s\n' "${job_id}"
}

run_adf_delivery() {
  local parameters run_id status details
  parameters="$(
    jq -cn \
      --arg sourceBaseUrl "${source_base_url}" \
      --arg sourceRelativeUrl "${source_relative_url}" \
      --arg sourceFileName "${source_file_name}" \
      '{
        sourceBaseUrl: $sourceBaseUrl,
        sourceRelativeUrl: $sourceRelativeUrl,
        sourceFileName: $sourceFileName,
        rawRoot: "landing/uci/raw"
      }'
  )"
  run_id="$(
    "${az_cli}" datafactory pipeline create-run \
      --resource-group "${resource_group}" \
      --factory-name "${factory_name}" \
      --name pl_ingest_uci_to_adls \
      --parameters "${parameters}" \
      --query runId \
      --output tsv
  )"
  echo "STAGE5_ADF_STARTED run_id=${run_id}" >&2

  for _ in $(seq 1 120); do
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
        details="$(
          "${az_cli}" datafactory pipeline-run show \
            --resource-group "${resource_group}" \
            --factory-name "${factory_name}" \
            --run-id "${run_id}" \
            --query '{runId:runId,status:status,runStart:runStart,runEnd:runEnd,durationInMs:durationInMs}' \
            --output json
        )"
        jq -c --arg raw_path "${lake_abfss}/landing/uci/raw/${run_id}/${source_file_name}" \
          '. + {rawPath: $raw_path}' <<<"${details}"
        return 0
        ;;
      Failed|Cancelled)
        details="$(
          "${az_cli}" datafactory pipeline-run show \
            --resource-group "${resource_group}" \
            --factory-name "${factory_name}" \
            --run-id "${run_id}" \
            --query '{status:status,message:message}' \
            --output json
        )"
        echo "STAGE5_ADF_FAILED run_id=${run_id} details=${details}" >&2
        return 1
        ;;
    esac
    sleep 5
  done
  echo "STAGE5_ADF_TIMEOUT run_id=${run_id}" >&2
  return 1
}

resume_adf_delivery() {
  local run_id="$1"
  local details status
  if [[ ! "${run_id}" =~ ^[a-f0-9-]{36}$ ]]; then
    echo "RETAILPULSE_STAGE5_RESUME_ADF_RUN_ID is not a UUID." >&2
    return 2
  fi
  details="$(
    "${az_cli}" datafactory pipeline-run show \
      --resource-group "${resource_group}" \
      --factory-name "${factory_name}" \
      --run-id "${run_id}" \
      --query '{runId:runId,status:status,runStart:runStart,runEnd:runEnd,durationInMs:durationInMs}' \
      --output json
  )"
  status="$(jq -r '.status' <<<"${details}")"
  if [[ "${status}" != "Succeeded" ]]; then
    echo "Cannot resume ADF run ${run_id}; status is ${status}." >&2
    return 1
  fi
  echo "STAGE5_ADF_RESUMED run_id=${run_id}" >&2
  jq -c --arg raw_path "${lake_abfss}/landing/uci/raw/${run_id}/${source_file_name}" \
    '. + {rawPath: $raw_path}' <<<"${details}"
}

run_databricks_normalization() {
  local job_id="$1"
  local adf_run_id="$2"
  local raw_path="$3"
  local normalized_root run_body run_id run state result_state task_run_id output result
  normalized_root="${lake_abfss}/landing/uci/normalized/${adf_run_id}"
  run_body="$(
    jq -cn \
      --argjson job_id "${job_id}" \
      --arg raw_path "${raw_path}" \
      --arg normalized_root "${normalized_root}" \
      --arg adf_pipeline_run_id "${adf_run_id}" \
      --arg expected_sha256 "${expected_sha256}" \
      --arg expected_size_bytes "${expected_size_bytes}" \
      '{
        job_id: $job_id,
        notebook_params: {
          raw_path: $raw_path,
          normalized_root: $normalized_root,
          adf_pipeline_run_id: $adf_pipeline_run_id,
          expected_sha256: $expected_sha256,
          expected_size_bytes: $expected_size_bytes
        }
      }'
  )"
  run_id="$(databricks_post "/api/2.2/jobs/run-now" "${run_body}" | jq -r '.run_id')"
  echo "STAGE5_DATABRICKS_STARTED adf_run_id=${adf_run_id} job_run_id=${run_id}" >&2

  for _ in $(seq 1 180); do
    run="$(databricks_get "/api/2.2/jobs/runs/get?run_id=${run_id}")"
    state="$(jq -r '.state.life_cycle_state' <<<"${run}")"
    if [[ "${state}" == "TERMINATED" || "${state}" == "INTERNAL_ERROR" || "${state}" == "SKIPPED" ]]; then
      result_state="$(jq -r '.state.result_state // "UNKNOWN"' <<<"${run}")"
      if [[ "${result_state}" != "SUCCESS" ]]; then
        echo "STAGE5_DATABRICKS_FAILED adf_run_id=${adf_run_id} job_run_id=${run_id} state=${result_state} message=$(jq -r '.state.state_message' <<<"${run}")" >&2
        return 1
      fi
      task_run_id="$(jq -r '.tasks[0].run_id' <<<"${run}")"
      output="$(databricks_get "/api/2.2/jobs/runs/get-output?run_id=${task_run_id}")"
      result="$(jq -r '.notebook_output.result' <<<"${output}")"
      jq -c \
        --argjson job_id "${job_id}" \
        --argjson job_run_id "${run_id}" \
        '. + {job_id: $job_id, job_run_id: $job_run_id}' <<<"${result}"
      return 0
    fi
    sleep 10
  done
  echo "STAGE5_DATABRICKS_TIMEOUT adf_run_id=${adf_run_id} job_run_id=${run_id}" >&2
  return 1
}

deliver_once() {
  local job_id="$1"
  local existing_adf_run_id="${2:-}"
  local adf_result adf_run_id raw_path normalization
  if [[ -n "${existing_adf_run_id}" ]]; then
    adf_result="$(resume_adf_delivery "${existing_adf_run_id}")" || return 1
  else
    adf_result="$(run_adf_delivery)" || return 1
  fi
  adf_run_id="$(jq -r '.runId' <<<"${adf_result}")"
  raw_path="$(jq -r '.rawPath' <<<"${adf_result}")"
  normalization="$(run_databricks_normalization "${job_id}" "${adf_run_id}" "${raw_path}")" \
    || return 1
  jq -cn --argjson adf "${adf_result}" --argjson normalization "${normalization}" \
    '{adf: $adf, normalization: $normalization}'
}

echo "Deploying Stage 5 ADF assets and unscheduled serverless normalization job." >&2
deploy_adf_assets
job_id="$(deploy_databricks_job)"
echo "STAGE5_JOB_READY job_id=${job_id} performance_target=STANDARD schedule=none" >&2

first="$(deliver_once "${job_id}" "${resume_adf_run_id}")"
if [[ "${verify_existing_only}" == "true" ]]; then
  if [[ -z "${resume_adf_run_id}" ]]; then
    echo "RETAILPULSE_STAGE5_VERIFY_EXISTING_ONLY requires a resume ADF run ID." >&2
    exit 2
  fi
  jq -cn \
    --argjson job_id "${job_id}" \
    --argjson verification "${first}" \
    '{
      status: "STAGE5_EXISTING_DELIVERY_VERIFIED",
      job_id: $job_id,
      verification: $verification
    }'
  exit 0
fi
second="$(deliver_once "${job_id}")"
first_run_id="$(jq -r '.adf.runId' <<<"${first}")"
second_run_id="$(jq -r '.adf.runId' <<<"${second}")"

if [[ "${first_run_id}" == "${second_run_id}" ]]; then
  echo "ADF rerun reused a pipeline run ID; immutable-delivery policy failed." >&2
  exit 1
fi
if ! jq -e --argjson first "$(jq '.normalization.counts' <<<"${first}")" \
  '.normalization.counts == $first' <<<"${second}" >/dev/null; then
  echo "Normalized record counts changed across identical source deliveries." >&2
  exit 1
fi

jq -cn \
  --argjson job_id "${job_id}" \
  --argjson first "${first}" \
  --argjson second "${second}" \
  '{
    status: "STAGE5_HISTORICAL_INGESTION_OK",
    job_id: $job_id,
    delivery_policy: "one immutable raw and normalized path per ADF pipeline run ID",
    first: $first,
    second: $second
  }'
