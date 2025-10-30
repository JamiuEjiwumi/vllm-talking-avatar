locals {
  rg_name      = "${var.project}-rg"
  acr_name     = replace("${var.project}acr", "-", "")
  aks_name     = "${var.project}-aks"
  sa_name      = substr(replace("${var.project}sa", "-", ""), 0, 22)
  ns           = "vllm"
  models_share = "models"
  voices_share = "voices"
  full_image   = "${azurerm_container_registry.acr.login_server}/${var.image_name}:${var.image_tag}"
}

# ---------------- Resource Group ----------------
resource "azurerm_resource_group" "rg" {
  name     = local.rg_name
  location = var.location
  tags = {
    project     = var.project
    environment = "test"
  }
}

# ---------------- ACR ----------------
resource "azurerm_container_registry" "acr" {
  name                = local.acr_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = true
}

# ---------------- Storage (Azure Files) ----------------
resource "azurerm_storage_account" "sa" {
  name                     = local.sa_name
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_share" "models" {
  name                 = local.models_share
  storage_account_name = azurerm_storage_account.sa.name
  quota                = 200 # Adjust for larger models if needed
}

resource "azurerm_storage_share" "voices" {
  name                 = local.voices_share
  storage_account_name = azurerm_storage_account.sa.name
  quota                = 20 # Adjust for larger voice files if needed
}

# ---------------- AKS (CPU system + GPU user pool) ----------------
resource "azurerm_kubernetes_cluster" "aks" {
  name                = local.aks_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "${var.project}-dns"
  sku_tier            = "Standard"
  oidc_issuer_enabled = true
  workload_identity_enabled = true

  default_node_pool {
    name       = "sys"
    vm_size    = "Standard_D2s_v3" # Changed to v3 to avoid quota issue; revert to v5 after quota increase
    node_count = 1
    type       = "VirtualMachineScaleSets"
    os_sku     = "Ubuntu"
  }

  identity {
    type = "SystemAssigned"
  }
}

# Allow AKS kubelet to pull from ACR
resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
}

# GPU pool
resource "azurerm_kubernetes_cluster_node_pool" "gpu" {
  name                  = "gpu"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id
  vm_size               = "Standard_NC6s_v3" # 1x V100 16GB
  node_count            = 1
  mode                  = "User"
  os_sku                = "Ubuntu"
  orchestrator_version  = azurerm_kubernetes_cluster.aks.kubernetes_version
  node_taints           = ["sku=gpu:NoSchedule"]
}

# --------------- Kube provider ---------------
data "azurerm_kubernetes_cluster" "aks" {
  name                = azurerm_kubernetes_cluster.aks.name
  resource_group_name = azurerm_resource_group.rg.name
}

provider "kubernetes" {
  host                   = data.azurerm_kubernetes_cluster.aks.kube_config[0].host
  client_certificate     = base64decode(data.azurerm_kubernetes_cluster.aks.kube_config[0].client_certificate)
  client_key             = base64decode(data.azurerm_kubernetes_cluster.aks.kube_config[0].client_key)
  cluster_ca_certificate = base64decode(data.azurerm_kubernetes_cluster.aks.kube_config[0].cluster_ca_certificate)
}

# --------------- K8s Namespace ---------------

resource "time_sleep" "wait_for_aks" {
  depends_on      = [azurerm_kubernetes_cluster.aks]
  create_duration = "60s"
}

resource "kubernetes_namespace" "ns" {
  metadata {
    name = local.ns
  }
  depends_on = [time_sleep.wait_for_aks]
}

# Secret for Azure Files
resource "kubernetes_secret" "azurefile" {
  metadata {
    name      = "azure-file-secret"
    namespace = kubernetes_namespace.ns.metadata[0].name
  }
  data = {
    azurestorageaccountname = azurerm_storage_account.sa.name
    azurestorageaccountkey  = azurerm_storage_account.sa.primary_access_key
  }
  type       = "Opaque"
  depends_on = [kubernetes_namespace.ns]
}

# ---------------- Build & Push image to ACR ----------------
resource "null_resource" "acr_build" {
  triggers = {
    image_tag       = var.image_tag
    image_name      = var.image_name
    acr_login       = azurerm_container_registry.acr.login_server
    app_src         = var.app_src_path
    dockerfile_hash = filesha1("${path.module}/../${var.dockerfile_path}")
  }

  provisioner "local-exec" {
    working_dir = var.app_src_path
    command     = <<EOT
      az acr login -n ${azurerm_container_registry.acr.name} || { echo "ACR login failed"; exit 1; }
      az acr build -r ${azurerm_container_registry.acr.name} -t ${local.full_image} . || { echo "ACR build failed"; exit 1; }
    EOT
    interpreter = ["/bin/bash", "-c"]
  }

  depends_on = [azurerm_container_registry.acr]
}

# Wait for ACR to index the image
resource "time_sleep" "post_build_pause" {
  depends_on      = [null_resource.acr_build]
  create_duration = "30s"
}

# ---------------- Deployment (GPU) ----------------
resource "kubernetes_deployment" "app" {
  metadata {
    name      = "vllm"
    namespace = kubernetes_namespace.ns.metadata[0].name
    labels    = { app = "vllm" }
  }
  depends_on = [
    time_sleep.post_build_pause,
    azurerm_kubernetes_cluster_node_pool.gpu,
    azurerm_role_assignment.acr_pull,
    kubernetes_namespace.ns
  ]

  spec {
    replicas = 1
    selector {
      match_labels = { app = "vllm" }
    }
    template {
      metadata {
        labels = { app = "vllm" }
      }
      spec {
        toleration {
          key      = "sku"
          operator = "Equal"
          value    = "gpu"
          effect   = "NoSchedule"
        }
        node_selector = { "kubernetes.azure.com/agentpool" = "gpu" }

        container {
          name  = "vllm"
          image = local.full_image
          port {
            container_port = var.container_port
          }
          resources {
            limits = {
              "nvidia.com/gpu" = tostring(var.gpu_count)
              cpu              = tostring(var.cpu)
              memory           = "${var.memory_gb}Gi"
            }
            requests = {
              "nvidia.com/gpu" = tostring(var.gpu_count)
              cpu              = tostring(var.cpu * 0.8) # Slightly lower for testing
              memory           = "${var.memory_gb * 0.8}Gi"
            }
          }
          env {
            name  = "PIPER_BIN"
            value = var.env_vars["PIPER_BIN"]
          }
          env {
            name  = "PIPER_VOICE"
            value = var.env_vars["PIPER_VOICE"]
          }
          env {
            name  = "WAV2LIP_CHECKPOINT"
            value = var.env_vars["WAV2LIP_CHECKPOINT"]
          }
          # Removed INFINITETALK_CHECKPOINT as per your request
          volume_mount {
            name       = "models"
            mount_path = "/mnt/models"
          }
          volume_mount {
            name       = "voices"
            mount_path = "/mnt/voices"
          }
          liveness_probe {
            http_get {
              path = "/health" # Adjust based on your app's health endpoint
              port = var.container_port
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }
          readiness_probe {
            http_get {
              path = "/health" # Adjust based on your app's health endpoint
              port = var.container_port
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
        volume {
          name = "models"
          azure_file {
            secret_name = kubernetes_secret.azurefile.metadata[0].name
            share_name  = azurerm_storage_share.models.name
            read_only   = false
          }
        }
        volume {
          name = "voices"
          azure_file {
            secret_name = kubernetes_secret.azurefile.metadata[0].name
            share_name  = azurerm_storage_share.voices.name
            read_only   = false
          }
        }
      }
    }
  }
}

# ---------------- Service (ClusterIP for internal access) ----------------
resource "kubernetes_service" "svc" {
  metadata {
    name      = "vllm-svc"
    namespace = kubernetes_namespace.ns.metadata[0].name
    labels    = { app = "vllm" }
  }
  depends_on = [kubernetes_namespace.ns]

  spec {
    selector = { app = "vllm" }
    type     = "ClusterIP"
    port {
      name        = "http"
      port        = 80
      target_port = var.container_port
      protocol    = "TCP"
    }
  }
}

# ---------------- Outputs ----------------
output "acr_login_server" {
  value       = azurerm_container_registry.acr.login_server
  description = "ACR login server for pushing images"
}

output "storage_account" {
  value       = azurerm_storage_account.sa.name
  description = "Storage account name for Azure Files"
}

output "aks_cluster_name" {
  value       = azurerm_kubernetes_cluster.aks.name
  description = "AKS cluster name for kubectl configuration"
}

output "test_instructions" {
  value       = <<EOT
To test the deployment:
1. Configure kubectl:
   az aks get-credentials -n ${azurerm_kubernetes_cluster.aks.name} -g ${azurerm_resource_group.rg.name} --overwrite-existing
2. Port-forward to the service:
   kubectl -n ${local.ns} port-forward svc/vllm-svc ${var.container_port}:${var.container_port}
3. Open in browser: http://localhost:${var.container_port}
EOT
  description = "Instructions to test the internal service"
}