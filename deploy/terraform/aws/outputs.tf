output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_ca_certificate" {
  description = "EKS cluster CA certificate (base64)"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.decepticon.endpoint
}

output "rds_database_url" {
  description = "Full PostgreSQL connection string for Helm values"
  value       = "postgresql://decepticon:${var.db_password}@${aws_db_instance.decepticon.endpoint}/litellm"
  sensitive   = true
}

output "ecr_repository_urls" {
  description = "ECR repository URLs for container images"
  value       = { for k, v in aws_ecr_repository.images : k => v.repository_url }
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.aws_region}"
}
