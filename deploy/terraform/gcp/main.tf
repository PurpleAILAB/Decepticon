terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------
resource "google_compute_network" "decepticon" {
  name                    = "${var.name_prefix}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "nodes" {
  name          = "${var.name_prefix}-nodes"
  ip_cidr_range = var.nodes_cidr
  region        = var.region
  network       = google_compute_network.decepticon.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }

  private_ip_google_access = true
}

resource "google_compute_router" "router" {
  name    = "${var.name_prefix}-router"
  region  = var.region
  network = google_compute_network.decepticon.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.name_prefix}-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# ---------------------------------------------------------------------------
# GKE Cluster
# ---------------------------------------------------------------------------
resource "google_container_cluster" "decepticon" {
  name     = var.name_prefix
  location = var.region

  network    = google_compute_network.decepticon.id
  subnetwork = google_compute_subnetwork.nodes.id

  # Use separately managed node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  release_channel {
    channel = "REGULAR"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }

  resource_labels = {
    project     = "decepticon"
    environment = var.environment
    managed-by  = "terraform"
  }
}

resource "google_container_node_pool" "default" {
  name     = "${var.name_prefix}-pool"
  location = var.region
  cluster  = google_container_cluster.decepticon.name

  initial_node_count = var.node_desired_count

  autoscaling {
    min_node_count = var.node_min_count
    max_node_count = var.node_max_count
  }

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = 100
    disk_type    = "pd-ssd"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      role = "decepticon"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# ---------------------------------------------------------------------------
# Cloud SQL PostgreSQL
# ---------------------------------------------------------------------------
resource "google_sql_database_instance" "decepticon" {
  name             = "${var.name_prefix}-postgres"
  region           = var.region
  database_version = "POSTGRES_17"

  settings {
    tier              = var.cloudsql_tier
    availability_type = var.environment == "production" ? "REGIONAL" : "ZONAL"

    disk_size         = 20
    disk_autoresize   = true
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.environment == "production"
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.decepticon.id
    }

    user_labels = {
      component = "postgres"
    }
  }

  deletion_protection = var.environment == "production"
}

resource "google_sql_database" "litellm" {
  name     = "litellm"
  instance = google_sql_database_instance.decepticon.name
}

resource "google_sql_user" "decepticon" {
  name     = "decepticon"
  instance = google_sql_database_instance.decepticon.name
  password = var.db_password
}

# ---------------------------------------------------------------------------
# Artifact Registry
# ---------------------------------------------------------------------------
resource "google_artifact_registry_repository" "decepticon" {
  location      = var.region
  repository_id = var.name_prefix
  format        = "DOCKER"
  description   = "Decepticon container images"

  labels = {
    project = "decepticon"
  }
}
