output "resource_group_name" { value = azurerm_resource_group.this.name }
output "storage_account_name" { value = azurerm_storage_account.lake.name }
output "eventhub_namespace" { value = azurerm_eventhub_namespace.this.name }
output "data_factory_name" { value = azurerm_data_factory.this.name }
output "databricks_workspace_url" { value = azurerm_databricks_workspace.this.workspace_url }
