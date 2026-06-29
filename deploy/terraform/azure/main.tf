terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  backend "azurerm" {}
}

provider "azurerm" {
  features {}
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "decepticon" {
  name     = "${var.name_prefix}-rg"
  location = var.location

  tags = {
    Project     = "decepticon"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Virtual Network
# ---------------------------------------------------------------------------
resource "azurerm_virtual_network" "decepticon" {
  name                = "${var.name_prefix}-vnet"
  location            = azurerm_resource_group.decepticon.location
  resource_group_name = azurerm_resource_group.decepticon.name
  address_space       = [var.vnet_cidr]
}

resource "azurerm_subnet" "aks" {
  name                 = "${var.name_prefix}-aks-subnet"
  resource_group_name  = azurerm_resource_group.decepticon.name
  virtual_network_name = azurerm_virtual_network.decepticon.name
  address_prefixes     = [var.aks_subnet_cidr]
}

resource "azurerm_subnet" "postgres" {
  name                 = "${var.name_prefix}-pg-subnet"
  resource_group_name  = azurerm_resource_group.decepticon.name
  virtual_network_name = azurerm_virtual_network.decepticon.name
  address_prefixes     = [var.postgres_subnet_cidr]

  delegation {
    name = "postgres-delegation"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "postgres" {
  name                = "${var.name_prefix}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.decepticon.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "${var.name_prefix}-pg-dns-link"
  resource_group_name   = azurerm_resource_group.decepticon.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.decepticon.id
}

# ---------------------------------------------------------------------------
# AKS Cluster
# ---------------------------------------------------------------------------
resource "azurerm_kubernetes_cluster" "decepticon" {
  name                = var.name_prefix
  location            = azurerm_resource_group.decepticon.location
  resource_group_name = azurerm_resource_group.decepticon.name
  dns_prefix          = var.name_prefix
  kubernetes_version  = var.kubernetes_version

  default_node_pool {
    name                = "default"
    vm_size             = var.node_vm_size
    min_count           = var.node_min_count
    max_count           = var.node_max_count
    auto_scaling_enabled = true
    vnet_subnet_id      = azurerm_subnet.aks.id

    node_labels = {
      role = "decepticon"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    network_policy = "calico"
    service_cidr   = var.service_cidr
    dns_service_ip = var.dns_service_ip
  }

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  tags = {
    Project     = "decepticon"
    Environment = var.environment
  }
}

# ---------------------------------------------------------------------------
# Azure Database for PostgreSQL Flexible Server
# ---------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "decepticon" {
  name                          = "${var.name_prefix}-postgres"
  location                      = azurerm_resource_group.decepticon.location
  resource_group_name           = azurerm_resource_group.decepticon.name
  version                       = "17"
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  administrator_login           = "decepticon"
  administrator_password        = var.db_password
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  zone                          = "1"

  high_availability {
    mode = var.environment == "production" ? "ZoneRedundant" : "Disabled"
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]

  tags = {
    Component = "postgres"
  }
}

resource "azurerm_postgresql_flexible_server_database" "litellm" {
  name      = "litellm"
  server_id = azurerm_postgresql_flexible_server.decepticon.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# ---------------------------------------------------------------------------
# Azure Container Registry
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "decepticon" {
  name                = replace("${var.name_prefix}acr", "-", "")
  location            = azurerm_resource_group.decepticon.location
  resource_group_name = azurerm_resource_group.decepticon.name
  sku                 = "Standard"
  admin_enabled       = false
}

resource "azurerm_role_assignment" "aks_acr_pull" {
  principal_id                     = azurerm_kubernetes_cluster.decepticon.kubelet_identity[0].object_id
  role_definition_name             = "AcrPull"
  scope                            = azurerm_container_registry.decepticon.id
  skip_service_principal_aad_check = true
}
