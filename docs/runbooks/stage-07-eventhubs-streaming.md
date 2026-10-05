# Stage 7 Event Hubs streaming runbook

Status: implemented and locally validated; live proof pending.

## What the runner does

```bash
./scripts/run_stage07_eventhubs_streaming.sh
```

The runner is intentionally all-or-cleanup. It:

1. Refreshes Terraform state and rejects the enable plan unless it contains exactly four creates:
   one Standard Event Hubs namespace and the three RetailPulse hubs.
2. Applies the saved plan and creates a namespace authorization rule with only `Send` and `Listen`.
3. Stores the connection string in a session-specific Key Vault secret and a temporary
   Databricks-backed secret scope. Only the scope/key names enter job parameters.
4. Uploads one unscheduled `STANDARD` serverless job with no retries and a 30-minute timeout.
5. Publishes bounded normal, duplicate, late, malformed, and traffic-spike scenarios through the
   Event Hubs Kafka endpoint.
6. Processes them with `Trigger.AvailableNow`, one checkpoint, coordinate-idempotent Bronze MERGE,
   `event_id` Silver MERGE, quarantine, and audit tables.
7. Publishes 40 recovery events. An `AvailableNow` run intentionally fails after Delta commits but
   before checkpoint commit; a second run reuses the same checkpoint and must write zero Bronze or
   Silver rows while reconciling all 40 events.
8. Deletes the Databricks scope and Key Vault secret, applies `enable_event_hubs=false`, and verifies
   the namespace is absent. The EXIT/INT/TERM trap attempts this cleanup on failures too.

Azure Databricks serverless jobs explicitly reject processing-time Structured Streaming triggers,
so the deterministic post-commit/pre-checkpoint failure uses `AvailableNow` for both interruption
and recovery. This proves checkpoint replay without creating a classic cluster.

## Expected reconciliation

| Scenario | Bronze | Silver | Quarantine |
|---|---:|---:|---:|
| normal | 60 | 60 | 0 |
| duplicate | 60 | 41 | 0 |
| late-data | 60 | 40 | 20 |
| malformed | 40 | 30 | 10 |
| traffic-spike | 200 | 200 | 0 |
| checkpoint-recovery | 40 | 40 | 0 |
| **Total** | **460** | **411** | **30** |

Silver must contain 411 distinct event IDs. The recovery run's latest Bronze and Silver Delta
MERGEs must both report zero inserted rows.

## Secret and state boundary

- The application connection string is never printed, committed, passed as a notebook/job
  parameter, or declared as a Terraform resource attribute.
- The scoped authorization rule is created operationally after the namespace exists; its value is
  copied to Key Vault and the temporary Databricks scope, then both are deleted.
- AzureRM exposes the namespace's provider-generated default authorization values as sensitive
  computed fields in the encrypted remote Terraform state whenever the namespace exists. Access to
  that backend must remain restricted. The application does not retrieve or use those default keys.
- A new session-specific Key Vault secret name is used on every run because vault soft-delete
  prevents immediate reuse of a deleted name.

## Failure handling

If the runner exits non-zero, first verify cleanup:

```bash
./scripts/azure_cli.sh eventhubs namespace list \
  --resource-group rg-retailpulse-dev-rp999 \
  --query '[].name' --output tsv
```

The result must be empty. If it is not, run a reviewed disable plan and apply:

```bash
./scripts/terraform_azure.sh plan \
  -var-file=dev.tfvars -var=enable_event_hubs=false -out=stage07-disable.tfplan
./scripts/terraform_azure.sh apply stage07-disable.tfplan
```

Do not delete ADLS, the Databricks workspace, ADF, Key Vault, identities, budget, or remote state.
