# No Log Analytics workspace or implicit recipients. Enable only in a reviewed bounded plan.
locals {
  monitor_receiver_labels = toset(nonsensitive(keys(var.monitor_email_receivers)))
}

resource "azurerm_monitor_metric_alert" "adf_failed_runs" {
  count               = var.enable_cloud_monitoring ? 1 : 0
  name                = "alert-${local.prefix}-adf-failed-runs"
  resource_group_name = azurerm_resource_group.this.name
  scopes              = [azurerm_data_factory.this.id]
  description         = "Any failed RetailPulse ADF pipeline in the last 15 minutes."
  enabled             = true
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  auto_mitigate       = true
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.DataFactory/factories"
    metric_name      = "PipelineFailedRuns"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }

  dynamic "action" {
    for_each = length(local.monitor_receiver_labels) > 0 ? [1] : []
    content {
      action_group_id = azurerm_monitor_action_group.operator[0].id
    }
  }
}

resource "azurerm_monitor_action_group" "operator" {
  count               = var.enable_cloud_monitoring && length(local.monitor_receiver_labels) > 0 ? 1 : 0
  name                = "ag-${local.prefix}"
  resource_group_name = azurerm_resource_group.this.name
  short_name          = "RetailPulse"
  enabled             = true
  tags                = local.tags

  dynamic "email_receiver" {
    for_each = local.monitor_receiver_labels
    content {
      name                    = email_receiver.value
      email_address           = var.monitor_email_receivers[email_receiver.value]
      use_common_alert_schema = true
    }
  }
}

resource "azurerm_monitor_diagnostic_setting" "adf_archive" {
  count              = var.enable_cloud_monitoring && var.enable_adf_log_archive ? 1 : 0
  name               = "adf-run-archive"
  target_resource_id = azurerm_data_factory.this.id
  storage_account_id = azurerm_storage_account.lake.id

  dynamic "enabled_log" {
    for_each = toset(["PipelineRuns", "ActivityRuns", "TriggerRuns"])
    content {
      category = enabled_log.value
    }
  }
}
