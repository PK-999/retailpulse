locals {
  prefix = "${var.project_name}-${var.environment}-${var.name_suffix}"
  tags = merge(var.tags, {
    environment    = var.environment
    teardown_after = var.teardown_after
  })
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_consumption_budget_subscription" "this" {
  name            = "budget-${local.prefix}"
  subscription_id = "/subscriptions/${var.subscription_id}"
  amount          = var.monthly_budget_amount
  time_grain      = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", plantimestamp())
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_roles  = ["Owner"]
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_roles  = ["Owner"]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_roles  = ["Owner"]
  }
}

resource "azurerm_storage_account" "lake" {
  name                            = substr(replace("st${local.prefix}", "-", ""), 0, 24)
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_data_lake_gen2_filesystem" "lake" {
  name               = "retailpulse"
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_eventhub_namespace" "this" {
  count               = var.enable_event_hubs ? 1 : 0
  name                = "evhns-${local.prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Standard"
  capacity            = 1
  minimum_tls_version = "1.2"
  tags                = local.tags
}

resource "azurerm_eventhub" "topics" {
  for_each = var.enable_event_hubs ? toset([
    "customer-events",
    "order-events",
    "inventory-events",
  ]) : toset([])
  name              = each.value
  namespace_id      = azurerm_eventhub_namespace.this[0].id
  partition_count   = 2
  message_retention = 1
}

resource "azurerm_data_factory" "this" {
  name                = "adf-${local.prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  identity { type = "SystemAssigned" }
  tags = local.tags
}

resource "azurerm_databricks_workspace" "this" {
  name                        = "dbw-${local.prefix}"
  resource_group_name         = azurerm_resource_group.this.name
  location                    = azurerm_resource_group.this.location
  sku                         = "standard"
  managed_resource_group_name = "rg-dbw-${local.prefix}"
  tags                        = local.tags
}

resource "azurerm_key_vault" "this" {
  name                       = substr("kv-${local.prefix}", 0, 24)
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  tags                       = local.tags
}

data "azurerm_client_config" "current" {}
