locals {
  prefix = "${var.project_name}-${var.environment}-${var.name_suffix}"
  lake_paths = toset([
    "landing",
    "bronze",
    "silver",
    "gold",
    "checkpoints",
    "quarantine",
  ])
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

resource "azurerm_storage_data_lake_gen2_path" "lake" {
  for_each           = local.lake_paths
  path               = each.value
  filesystem_name    = azurerm_storage_data_lake_gen2_filesystem.lake.name
  storage_account_id = azurerm_storage_account.lake.id
  resource           = "directory"
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
  count                       = var.enable_databricks_workspace ? 1 : 0
  name                        = "dbw-${local.prefix}"
  resource_group_name         = azurerm_resource_group.this.name
  location                    = azurerm_resource_group.this.location
  sku                         = "premium"
  managed_resource_group_name = "rg-dbw-${local.prefix}"
  tags                        = local.tags
}

moved {
  from = azurerm_databricks_workspace.this
  to   = azurerm_databricks_workspace.this[0]
}

resource "azurerm_databricks_access_connector" "lake" {
  name                = "ac-dbw-${local.prefix}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
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

locals {
  lake_filesystem_scope = "${azurerm_storage_account.lake.id}/blobServices/default/containers/${azurerm_storage_data_lake_gen2_filesystem.lake.name}"
}

resource "azurerm_role_assignment" "adf_lake" {
  scope                            = local.lake_filesystem_scope
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_data_factory.this.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  description                      = "Allow RetailPulse ADF to land data in the project filesystem."
}

resource "azurerm_role_assignment" "databricks_lake" {
  scope                            = local.lake_filesystem_scope
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_databricks_access_connector.lake.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  description                      = "Allow the RetailPulse Databricks Access Connector to use the lake."
}

resource "azurerm_role_assignment" "databricks_delegator" {
  scope                            = azurerm_storage_account.lake.id
  role_definition_name             = "Storage Blob Delegator"
  principal_id                     = azurerm_databricks_access_connector.lake.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  description                      = "Allow Unity Catalog to request short-lived user delegation keys for the RetailPulse lake."
}

resource "azurerm_role_assignment" "adf_key_vault" {
  scope                            = azurerm_key_vault.this.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_data_factory.this.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
  description                      = "Allow RetailPulse ADF to read only the secrets needed by linked services."
}

resource "azurerm_role_assignment" "deployer_key_vault" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
  description          = "Allow the current deployment identity to create and rotate demo secrets."
}

data "azurerm_client_config" "current" {}
