output "resource_group_name" { value = azurerm_resource_group.this.name }
output "storage_account_name" { value = azurerm_storage_account.lake.name }
output "filesystem_name" { value = azurerm_storage_data_lake_gen2_filesystem.lake.name }
output "lake_abfss_url" {
  value = "abfss://${azurerm_storage_data_lake_gen2_filesystem.lake.name}@${azurerm_storage_account.lake.name}.dfs.core.windows.net"
}
output "lake_directories" { value = sort(keys(azurerm_storage_data_lake_gen2_path.lake)) }
output "eventhub_namespace" { value = try(azurerm_eventhub_namespace.this[0].name, null) }
output "eventhub_names" { value = sort(keys(azurerm_eventhub.topics)) }
output "data_factory_name" { value = azurerm_data_factory.this.name }
output "databricks_workspace_url" { value = try(azurerm_databricks_workspace.this[0].workspace_url, null) }
output "databricks_access_connector_id" { value = azurerm_databricks_access_connector.lake.id }
output "databricks_access_connector_principal_id" {
  value = azurerm_databricks_access_connector.lake.identity[0].principal_id
}
output "adf_principal_id" { value = azurerm_data_factory.this.identity[0].principal_id }
output "key_vault_name" { value = azurerm_key_vault.this.name }
output "eventhubs_secret_name" { value = "eventhubs-kafka-connection-string" }
output "budget_name" { value = azurerm_consumption_budget_subscription.this.name }
