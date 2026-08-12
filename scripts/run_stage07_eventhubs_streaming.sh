#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
az_cli="${project_root}/scripts/azure_cli.sh"
tf_cli="${project_root}/scripts/terraform_azure.sh"
python_cli="${project_root}/.venv/bin/python"
databricks_resource="2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
notebook_path="/Shared/retailpulse/stage07/stream_bronze_silver"
job_name="retailpulse-stage07-eventhubs-streaming"
secret_scope="retailpulse-stage07"
secret_key_prefix="eventhubs-kafka-connection-string"
authorization_rule="retailpulse-streaming"
catalog_name="${RETAILPULSE_DATABRICKS_CATALOG:-dbw_retailpulse_dev_rp999}"
enable_plan="stage07-enable.tfplan"
disable_plan="stage07-disable.tfplan"
stream_run_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
checkpoint_namespace="stage07-${stream_run_id}"
secret_key="${secret_key_prefix}-${stream_run_id}"
event_hubs_enabled=false
scope_created=false
secret_created=false
secret_file="${project_root}/.azure/stage07-${stream_run_id}.secret"
secret_file_container="/work/.azure/stage07-${stream_run_id}.secret"
install -m 600 /dev/null "${secret_file}"

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

validate_event_hubs_plan() {
  local plan_file="$1"
  local expected_action="$2"
  local expected_count="${3:-4}"
  local plan_json changed_count
  plan_json="$(${tf_cli} show -json "${plan_file}")"
  changed_count="$(
    jq '[.resource_changes[]? | select(.change.actions != ["no-op"])] | length' \
      <<<"${plan_json}"
  )"
  if [[ "${expected_count}" == "exact" && "${changed_count}" != "4" ]]; then
    echo "Stage 7 enable plan must change exactly one namespace and three event hubs." >&2
    return 1
  fi
  if (( changed_count > 4 )); then
    echo "Stage 7 Terraform plan exceeds the four-resource Event Hubs boundary." >&2
    return 1
  fi
  jq -e --arg action "${expected_action}" '
    [.resource_changes[]? | select(.change.actions != ["no-op"])]
    | all(
        (.type == "azurerm_eventhub_namespace" or .type == "azurerm_eventhub")
        and (.change.actions == [$action])
      )
  ' <<<"${plan_json}" >/dev/null
}

disable_event_hubs() {
  ${tf_cli} plan -var-file=dev.tfvars -var=enable_event_hubs=false \
    -out="${disable_plan}" -input=false >/dev/null
  validate_event_hubs_plan "${disable_plan}" delete partial
  ${tf_cli} apply -input=false -auto-approve "${disable_plan}" >/dev/null
  event_hubs_enabled=false
  if [[ "$(
    "${az_cli}" eventhubs namespace list \
      --resource-group "${resource_group}" --query 'length(@)' --output tsv
  )" != "0" ]]; then
    echo "Event Hubs namespace still exists after Stage 7 cleanup." >&2
    return 1
  fi
}

cleanup() {
  local original_status=$?
  local cleanup_status=0
  trap - EXIT INT TERM
  set +e
  if ${scope_created}; then
    databricks_post "/api/2.0/secrets/scopes/delete" \
      "$(jq -cn --arg scope "${secret_scope}" '{scope:$scope}')" >/dev/null || cleanup_status=1
  fi
  if ${secret_created}; then
    "${az_cli}" keyvault secret delete --vault-name "${key_vault_name}" \
      --name "${secret_key}" --only-show-errors --output none || cleanup_status=1
  fi
  if ${event_hubs_enabled}; then
    disable_event_hubs || cleanup_status=1
  fi
  rm -f "${secret_file}" \
    "${project_root}/terraform/${enable_plan}" \
    "${project_root}/terraform/${disable_plan}"
  set -e
  if (( original_status != 0 )); then
    exit "${original_status}"
  fi
  exit "${cleanup_status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -x "${python_cli}" ]]; then
  echo "Create .venv and install the project Kafka extra before Stage 7." >&2
  exit 2
fi
if [[ ! "${stream_run_id}" =~ ^[a-f0-9-]{36}$ ]]; then
  echo "Unable to create a safe Stage 7 stream run ID." >&2
  exit 2
fi

resource_group="$(${tf_cli} output -raw resource_group_name)"
databricks_host="$(${tf_cli} output -raw databricks_workspace_url)"
lake_abfss="$(${tf_cli} output -raw lake_abfss_url)"
key_vault_name="$(${tf_cli} output -raw key_vault_name)"
workspace_url="https://${databricks_host}"
if [[ ! "${databricks_host}" =~ ^adb-[0-9]+\.[0-9]+\.azuredatabricks\.net$ ]]; then
  echo "The Terraform Databricks output is not a workspace hostname." >&2
  exit 2
fi
if [[ ! "${catalog_name}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "RETAILPULSE_DATABRICKS_CATALOG contains unsupported characters." >&2
  exit 2
fi

${tf_cli} plan -var-file=dev.tfvars -var=enable_event_hubs=true \
  -out="${enable_plan}" -input=false >/dev/null
validate_event_hubs_plan "${enable_plan}" create exact
event_hubs_enabled=true
${tf_cli} apply -input=false -auto-approve "${enable_plan}" >/dev/null

eventhub_namespace="$(${tf_cli} output -raw eventhub_namespace)"
bootstrap_servers="${eventhub_namespace}.servicebus.windows.net:9093"
"${az_cli}" eventhubs namespace authorization-rule create \
  --resource-group "${resource_group}" \
  --namespace-name "${eventhub_namespace}" \
  --name "${authorization_rule}" \
  --rights Listen Send --only-show-errors --output none
connection_string="$(
  "${az_cli}" eventhubs namespace authorization-rule keys list \
    --resource-group "${resource_group}" \
    --namespace-name "${eventhub_namespace}" \
    --name "${authorization_rule}" \
    --query primaryConnectionString --output tsv
)"
if [[ ! "${connection_string}" =~ ^Endpoint=sb:// ]]; then
  echo "Event Hubs did not return a namespace connection string." >&2
  exit 1
fi
printf '%s' "${connection_string}" >"${secret_file}"
"${az_cli}" keyvault secret set --vault-name "${key_vault_name}" \
  --name "${secret_key}" --file "${secret_file_container}" --encoding utf-8 \
  --only-show-errors --output none
secret_created=true

existing_scopes="$(databricks_get "/api/2.0/secrets/scopes/list")"
if jq -e --arg scope "${secret_scope}" '.scopes[]? | select(.name == $scope)' \
  <<<"${existing_scopes}" >/dev/null; then
  databricks_post "/api/2.0/secrets/scopes/delete" \
    "$(jq -cn --arg scope "${secret_scope}" '{scope:$scope}')" >/dev/null
fi
databricks_post "/api/2.0/secrets/scopes/create" \
  "$(jq -cn --arg scope "${secret_scope}" '{scope:$scope}')" \
  >/dev/null
scope_created=true
databricks_post "/api/2.0/secrets/put" \
  "$(jq -cn --arg scope "${secret_scope}" --arg key "${secret_key}" \
    --arg value "${connection_string}" \
    '{scope:$scope,key:$key,string_value:$value}')" >/dev/null
unset connection_string

content="$(base64 <"${project_root}/databricks/stream_bronze_silver.py" | tr -d '\n')"
databricks_post "/api/2.0/workspace/mkdirs" \
  "$(jq -cn --arg path "$(dirname "${notebook_path}")" '{path:$path}')" >/dev/null
databricks_post "/api/2.0/workspace/import" \
  "$(jq -cn --arg path "${notebook_path}" --arg content "${content}" \
    '{path:$path,format:"SOURCE",language:"PYTHON",overwrite:true,content:$content}')" \
  >/dev/null

job_settings="$(
  jq -cn --arg name "${job_name}" --arg notebook_path "${notebook_path}" '{
    name:$name,
    description:"Temporary authenticated Event Hubs checkpoint/Delta MERGE proof.",
    max_concurrent_runs:1,
    timeout_seconds:1800,
    performance_target:"STANDARD",
    queue:{enabled:true},
    tags:{project:"retailpulse",environment:"dev",stage:"07",profile:"azure"},
    tasks:[{
      task_key:"eventhubs_stream",
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
job_id="$(
  jq -r --arg name "${job_name}" \
    '.jobs[]? | select(.settings.name == $name) | .job_id' <<<"${jobs}" | head -n 1
)"
if [[ -n "${job_id}" ]]; then
  databricks_post "/api/2.2/jobs/reset" \
    "$(jq -cn --argjson job_id "${job_id}" --argjson settings "${job_settings}" \
      '{job_id:$job_id,new_settings:$settings}')" >/dev/null
else
  job_id="$(
    databricks_post "/api/2.2/jobs/create" "${job_settings}" | jq -r '.job_id'
  )"
fi

produce_scenario() {
  local scenario="$1"
  local count="$2"
  local seed="$3"
  KAFKA_ENABLED=true \
  KAFKA_BOOTSTRAP_SERVERS="${bootstrap_servers}" \
  KAFKA_SECURITY_PROTOCOL=SASL_SSL \
  KAFKA_SASL_MECHANISM=PLAIN \
  KAFKA_SASL_USERNAME='$ConnectionString' \
  KAFKA_SASL_PASSWORD="$(<"${secret_file}")" \
  KAFKA_RUN_ID="${stream_run_id}" \
    "${python_cli}" "${project_root}/scripts/generate_data.py" \
      --scale azure --count "${count}" --scenario "${scenario}" --seed "${seed}"
}

run_stream() {
  local trigger_mode="$1"
  local fail_after_batch="$2"
  local starting_offsets="$3"
  local expected_result="$4"
  local body run_id run state task_run_id output result_state
  body="$(
    jq -cn \
      --argjson job_id "${job_id}" \
      --arg kafka_bootstrap_servers "${bootstrap_servers}" \
      --arg base_path "${lake_abfss}" \
      --arg catalog_name "${catalog_name}" \
      --arg secret_scope "${secret_scope}" \
      --arg secret_key "${secret_key}" \
      --arg trigger_mode "${trigger_mode}" \
      --arg checkpoint_namespace "${checkpoint_namespace}" \
      --arg fail_after_committed_batch "${fail_after_batch}" \
      --arg starting_offsets "${starting_offsets}" \
      --arg stream_run_id "${stream_run_id}" '{
        job_id:$job_id,
        notebook_params:{
          kafka_bootstrap_servers:$kafka_bootstrap_servers,
          base_path:$base_path,
          catalog_name:$catalog_name,
          secret_scope:$secret_scope,
          secret_key:$secret_key,
          trigger_mode:$trigger_mode,
          max_runtime_minutes:"30",
          max_offsets_per_trigger:"5000",
          checkpoint_namespace:$checkpoint_namespace,
          fail_after_committed_batch:$fail_after_committed_batch,
          starting_offsets:$starting_offsets,
          stream_run_id:$stream_run_id
        }
      }'
  )"
  run_id="$(databricks_post "/api/2.2/jobs/run-now" "${body}" | jq -r '.run_id')"
  echo "STAGE7_JOB_STARTED trigger=${trigger_mode} run_id=${run_id}" >&2
  for _ in $(seq 1 180); do
    run="$(databricks_get "/api/2.2/jobs/runs/get?run_id=${run_id}")"
    state="$(jq -r '.state.life_cycle_state' <<<"${run}")"
    if [[ "${state}" == "TERMINATED" || "${state}" == "INTERNAL_ERROR" || \
          "${state}" == "SKIPPED" ]]; then
      result_state="$(jq -r '.state.result_state // "UNKNOWN"' <<<"${run}")"
      task_run_id="$(jq -r '.tasks[0].run_id' <<<"${run}")"
      output="$(databricks_get "/api/2.2/jobs/runs/get-output?run_id=${task_run_id}")"
      if [[ "${expected_result}" == "SUCCESS" && "${result_state}" != "SUCCESS" ]]; then
        jq '{error,error_trace,metadata}' <<<"${output}" >&2
        return 1
      fi
      if [[ "${expected_result}" == "INTENTIONAL_FAILURE" ]]; then
        if [[ "${result_state}" != "FAILED" ]] || \
           ! jq -e '[(.error // ""), (.error_trace // "")] | join(" ") |
             contains("STAGE7_INTENTIONAL_FAILURE_AFTER_COMMITTED_BATCH")' \
             <<<"${output}" >/dev/null; then
          echo "Stage 7 recovery run did not fail at the intentional checkpoint boundary." >&2
          return 1
        fi
        jq -cn --argjson job_run_id "${run_id}" --argjson task_run_id "${task_run_id}" \
          --arg result_state "${result_state}" \
          '{job_run_id:$job_run_id,task_run_id:$task_run_id,result_state:$result_state}'
        return 0
      fi
      jq -c --argjson job_run_id "${run_id}" --argjson task_run_id "${task_run_id}" \
        --argjson setup_ms "$(jq '.tasks[0].setup_duration' <<<"${run}")" \
        --argjson execution_ms "$(jq '.tasks[0].execution_duration' <<<"${run}")" \
        '.notebook_output.result | fromjson | . + {
          job_run_id:$job_run_id,
          task_run_id:$task_run_id,
          setup_duration_ms:$setup_ms,
          execution_duration_ms:$execution_ms
        }' <<<"${output}"
      return 0
    fi
    sleep 10
  done
  echo "Stage 7 job exceeded its orchestration polling window." >&2
  return 1
}

produce_scenario normal 60 101
produce_scenario duplicate 60 102
produce_scenario late-data 60 103
produce_scenario malformed 40 104
produce_scenario traffic-spike 20 105
initial_result="$(run_stream available_now false earliest SUCCESS)"

produce_scenario checkpoint-recovery 40 106
fault_result="$(run_stream available_now true earliest INTENTIONAL_FAILURE)"
recovery_result="$(run_stream available_now false earliest SUCCESS)"

jq -e '
  .scenario_counts.bronze.normal == 60 and
  .scenario_counts.bronze.duplicate == 60 and
  .scenario_counts.bronze["late-data"] == 60 and
  .scenario_counts.bronze.malformed == 40 and
  .scenario_counts.bronze["traffic-spike"] == 200 and
  .scenario_counts.bronze["checkpoint-recovery"] == 40 and
  .scenario_counts.silver.normal == 60 and
  .scenario_counts.silver.duplicate == 41 and
  .scenario_counts.silver["late-data"] == 40 and
  .scenario_counts.silver.malformed == 30 and
  .scenario_counts.silver["traffic-spike"] == 200 and
  .scenario_counts.silver["checkpoint-recovery"] == 40 and
  .scenario_counts.quarantine["late-data"] == 20 and
  .scenario_counts.quarantine.malformed == 10 and
  .bronze_total == 460 and .silver_total == 411 and
  .silver_unique_event_ids == 411 and .quarantine_total == 30 and
  (.audit_results | length) == 2 and
  (.audit_results[] | select(.batch_id == 1) | .records_read) == 40 and
  (.audit_results[] | select(.batch_id == 1) |
    .silver_history.numTargetRowsInserted) == 0 and
  (.audit_results[] | select(.batch_id == 1) |
    .bronze_history.numTargetRowsInserted) == 0
' <<<"${recovery_result}" >/dev/null

final_result="$(
  jq -cn \
    --arg status "STAGE7_EVENTHUBS_STREAMING_VERIFIED" \
    --arg stream_run_id "${stream_run_id}" \
    --argjson job_id "${job_id}" \
    --argjson initial "${initial_result}" \
    --argjson fault "${fault_result}" \
    --argjson recovery "${recovery_result}" \
    '{status:$status,stream_run_id:$stream_run_id,job_id:$job_id,
      initial:$initial,fault:$fault,recovery:$recovery}'
)"

databricks_post "/api/2.0/secrets/scopes/delete" \
  "$(jq -cn --arg scope "${secret_scope}" '{scope:$scope}')" >/dev/null
scope_created=false
"${az_cli}" keyvault secret delete --vault-name "${key_vault_name}" \
  --name "${secret_key}" --only-show-errors --output none
secret_created=false
disable_event_hubs

if [[ "$(databricks_get "/api/2.2/jobs/runs/list?active_only=true&limit=26" | \
  jq '.runs // [] | length')" != "0" ]]; then
  echo "A Databricks job run remains active after Stage 7." >&2
  exit 1
fi

printf '%s\n' "${final_result}"
