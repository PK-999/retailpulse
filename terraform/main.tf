resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

locals {
  prefix = "${var.project_name}-${var.environment}-${random_string.suffix.result}"
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = var.tags
}

resource "azurerm_storage_account" "lake" {
  name                     = substr(replace("st${local.prefix}", "-", ""), 0, 24)
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled           = true
  min_tls_version          = "TLS1_2"
  tags                     = var.tags
}

resource "azurerm_storage_data_lake_gen2_filesystem" "lake" {
  name               = "retailpulse"
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_eventhub_namespace" "this" {
  name                = "evhns-${local.prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Standard"
  capacity            = 1
  tags                = var.tags
}

resource "azurerm_eventhub" "topics" {
  for_each            = toset(["customer-events", "order-events", "inventory-events"])
  name                = each.value
  namespace_name      = azurerm_eventhub_namespace.this.name
  resource_group_name = azurerm_resource_group.this.name
  partition_count     = 2
  message_retention   = 1
}

resource "azurerm_data_factory" "this" {
  name                = "adf-${local.prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  identity { type = "SystemAssigned" }
  tags = var.tags
}

resource "azurerm_databricks_workspace" "this" {
  name                = "dbw-${local.prefix}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "standard"
  tags                = var.tags
}

resource "azurerm_key_vault" "this" {
  name                       = substr("kv-${local.prefix}", 0, 24)
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  soft_delete_retention_days = 7
  tags                       = var.tags
}

data "azurerm_client_config" "current" {}
