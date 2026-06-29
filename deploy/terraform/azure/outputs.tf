output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.decepticon.name
}

output "aks_cluster_name" {
  description = "AKS cluster name"
  value       = azurerm_kubernetes_cluster.decepticon.name
}

output "aks_cluster_fqdn" {
  description = "AKS cluster FQDN"
  value       = azurerm_kubernetes_cluster.decepticon.fqdn
}

output "aks_kube_config" {
  description = "AKS kubeconfig (raw)"
  value       = azurerm_kubernetes_cluster.decepticon.kube_config_raw
  sensitive   = true
}

output "postgres_fqdn" {
  description = "PostgreSQL Flexible Server FQDN"
  value       = azurerm_postgresql_flexible_server.decepticon.fqdn
}

output "database_url" {
  description = "Full PostgreSQL connection string for Helm values"
  value       = "postgresql://decepticon:${var.db_password}@${azurerm_postgresql_flexible_server.decepticon.fqdn}:5432/litellm?sslmode=require"
  sensitive   = true
}

output "acr_login_server" {
  description = "ACR login server URL"
  value       = azurerm_container_registry.decepticon.login_server
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.decepticon.name} --name ${azurerm_kubernetes_cluster.decepticon.name}"
}
