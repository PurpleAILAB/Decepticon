output "gke_cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.decepticon.name
}

output "gke_cluster_endpoint" {
  description = "GKE cluster API endpoint"
  value       = google_container_cluster.decepticon.endpoint
  sensitive   = true
}

output "gke_cluster_ca_certificate" {
  description = "GKE cluster CA certificate (base64)"
  value       = google_container_cluster.decepticon.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "cloudsql_connection_name" {
  description = "Cloud SQL connection name for the proxy"
  value       = google_sql_database_instance.decepticon.connection_name
}

output "cloudsql_private_ip" {
  description = "Cloud SQL private IP"
  value       = google_sql_database_instance.decepticon.private_ip_address
}

output "database_url" {
  description = "Full PostgreSQL connection string for Helm values"
  value       = "postgresql://decepticon:${var.db_password}@${google_sql_database_instance.decepticon.private_ip_address}:5432/litellm"
  sensitive   = true
}

output "artifact_registry_url" {
  description = "Artifact Registry Docker URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.decepticon.repository_id}"
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.decepticon.name} --region ${var.region} --project ${var.project_id}"
}
