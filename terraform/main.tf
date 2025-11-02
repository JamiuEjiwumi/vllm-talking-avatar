########################################
# Locals
########################################
locals {
  rg_name  = "${var.project}-rg"
  acr_name = replace("${var.project}acr", "-", "")
  sa_name  = substr(replace("${var.project}sa", "-", ""), 0, 22)

  models_share  = "models"
  voices_share  = "voices"
  outputs_share = "outputs"

  image_full = "${azurerm_container_registry.acr.login_server}/${var.image_name}:${var.image_tag}"
}

########################################
# Resource Group
########################################
resource "azurerm_resource_group" "rg" {
  name     = local.rg_name
  location = var.location
  tags = {
    project     = var.project
    environment = "test"
  }
}

########################################
# ACR
########################################
resource "azurerm_container_registry" "acr" {
  name                = local.acr_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Basic"
  admin_enabled       = true
}

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
      az acr login -n ${azurerm_container_registry.acr.name} || exit 1
      az acr build -r ${azurerm_container_registry.acr.name} -t ${var.image_name}:${var.image_tag} . || exit 1
    EOT
    interpreter = ["/bin/bash", "-c"]
  }

  depends_on = [azurerm_container_registry.acr]
}

resource "time_sleep" "after_build" {
  create_duration = "30s"
  depends_on      = [null_resource.acr_build]
}

########################################
# Storage (Azure Files)
########################################
resource "azurerm_storage_account" "sa" {
  count                    = var.use_azure_files ? 1 : 0
  name                     = local.sa_name
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_share" "models" {
  count                = var.use_azure_files ? 1 : 0
  name                 = local.models_share
  storage_account_name = azurerm_storage_account.sa[0].name
  quota                = 200
}

resource "azurerm_storage_share" "voices" {
  count                = var.use_azure_files ? 1 : 0
  name                 = local.voices_share
  storage_account_name = azurerm_storage_account.sa[0].name
  quota                = 20
}

resource "azurerm_storage_share" "outputs" {
  count                = var.use_azure_files ? 1 : 0
  name                 = local.outputs_share
  storage_account_name = azurerm_storage_account.sa[0].name
  quota                = 50
}

########################################
# Log Analytics (ACA env requirement)
########################################
resource "azurerm_log_analytics_workspace" "law" {
  name                = "${var.project}-law"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

########################################
# Container Apps Environment
########################################
resource "azurerm_container_app_environment" "env" {
  name                       = "${var.project}-cae"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

# Register Azure Files with the environment
resource "azurerm_container_app_environment_storage" "models" {
  count                        = var.use_azure_files ? 1 : 0
  name                         = "models"
  container_app_environment_id = azurerm_container_app_environment.env.id
  account_name                 = azurerm_storage_account.sa[0].name
  share_name                   = azurerm_storage_share.models[0].name
  access_mode                  = "ReadWrite"
  access_key                   = azurerm_storage_account.sa[0].primary_access_key
}

resource "azurerm_container_app_environment_storage" "voices" {
  count                        = var.use_azure_files ? 1 : 0
  name                         = "voices"
  container_app_environment_id = azurerm_container_app_environment.env.id
  account_name                 = azurerm_storage_account.sa[0].name
  share_name                   = azurerm_storage_share.voices[0].name
  access_mode                  = "ReadWrite"
  access_key                   = azurerm_storage_account.sa[0].primary_access_key
}

resource "azurerm_container_app_environment_storage" "outputs" {
  count                        = var.use_azure_files ? 1 : 0
  name                         = "outputs"
  container_app_environment_id = azurerm_container_app_environment.env.id
  account_name                 = azurerm_storage_account.sa[0].name
  share_name                   = azurerm_storage_share.outputs[0].name
  access_mode                  = "ReadWrite"
  access_key                   = azurerm_storage_account.sa[0].primary_access_key
}

########################################
# Container App
########################################
resource "azurerm_container_app" "app" {
  name                         = "${var.project}-aca"
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-pwd"
  }

  secret {
    name  = "acr-pwd"
    value = azurerm_container_registry.acr.admin_password
  }

  secret {
    name  = "fal-api-key"
    value = var.fal_api_key
  }

  secret {
    name  = "did-api-key"
    value = var.d_id_api_key
  }

  dynamic "secret" {
    for_each = try(var.sadtalker_base, null) != null && var.sadtalker_base != "" ? [1] : []
    content {
      name  = "sadtalker-base"
      value = var.sadtalker_base
    }
  }

  ingress {
    external_enabled = true
    target_port      = var.app_port
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    container {
      name   = "web"
      image  = local.image_full
      cpu    = 1.0
      memory = "2Gi"

      # --- ENV (ALL MULTI-LINE) ---

      # Port
      env {
        name  = "PORT"
        value = tostring(var.app_port)
      }

      # Streamlit/general env (non-secrets)
      env {
        name  = "STREAMLIT_SERVER_HEADLESS"
        value = lookup(var.app_env, "STREAMLIT_SERVER_HEADLESS", "true")
      }
      env {
        name  = "STREAMLIT_SERVER_ADDRESS"
        value = lookup(var.app_env, "STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
      }
      env {
        name  = "STREAMLIT_BROWSER_GATHERUSAGESTATS"
        value = lookup(var.app_env, "STREAMLIT_BROWSER_GATHERUSAGESTATS", "false")
      }
      env {
        name  = "STREAMLIT_SERVER_FILEWATCHER_TYPE"
        value = lookup(var.app_env, "STREAMLIT_SERVER_FILEWATCHER_TYPE", "none")
      }

      env {
        name  = "ORT_LOG_SEVERITY_LEVEL"
        value = lookup(var.app_env, "ORT_LOG_SEVERITY_LEVEL", "3")
      }

      env {
        name  = "FAL_TIMEOUT"
        value = lookup(var.app_env, "FAL_TIMEOUT", "1800")
      }
      env {
        name  = "FAL_REQ_TIMEOUT"
        value = lookup(var.app_env, "FAL_REQ_TIMEOUT", "45")
      }
      env {
        name  = "FAL_POLL_EVERY"
        value = lookup(var.app_env, "FAL_POLL_EVERY", "2.0")
      }
      env {
        name  = "FAL_RESPONSE_GRACE"
        value = lookup(var.app_env, "FAL_RESPONSE_GRACE", "60")
      }
      env {
        name  = "FAL_CONC_BACKOFF_S"
        value = lookup(var.app_env, "FAL_CONC_BACKOFF_S", "5")
      }
      env {
        name  = "FAL_CONC_BACKOFF_MAX"
        value = lookup(var.app_env, "FAL_CONC_BACKOFF_MAX", "60")
      }
      env {
        name  = "FAL_MAX_SUBMIT_RETRIES"
        value = lookup(var.app_env, "FAL_MAX_SUBMIT_RETRIES", "40")
      }

      env {
        name  = "FAL_INF_ENDPOINT"
        value = lookup(var.app_env, "FAL_INF_ENDPOINT", "fal-ai/infinitalk/single-text")
      }
      env {
        name  = "FAL_QUEUE_BASE"
        value = lookup(var.app_env, "FAL_QUEUE_BASE", "https://queue.fal.run")
      }
      env {
        name  = "FAL_VEO3_ENDPOINT"
        value = lookup(var.app_env, "FAL_VEO3_ENDPOINT", "fal-ai/veo3")
      }

      env {
        name  = "SADTALKER_POSE_SCALE"
        value = lookup(var.app_env, "SADTALKER_POSE_SCALE", "1.2")
      }
      env {
        name  = "SADTALKER_EXPRESSION_SCALE"
        value = lookup(var.app_env, "SADTALKER_EXPRESSION_SCALE", "1.3")
      }
      env {
        name  = "SADTALKER_STILL_MODE"
        value = lookup(var.app_env, "SADTALKER_STILL_MODE", "false")
      }
      env {
        name  = "SADTALKER_PREPROCESS"
        value = lookup(var.app_env, "SADTALKER_PREPROCESS", "full")
      }
      env {
        name  = "SADTALKER_ENHANCER"
        value = lookup(var.app_env, "SADTALKER_ENHANCER", "gfpgan")
      }
      env {
        name  = "SADTALKER_TIMEOUT"
        value = lookup(var.app_env, "SADTALKER_TIMEOUT", "300")
      }

      env {
        name  = "PIPER_BIN"
        value = lookup(var.app_env, "PIPER_BIN", "/usr/local/bin/piper")
      }
      env {
        name  = "PIPER_VOICE"
        value = lookup(var.app_env, "PIPER_VOICE", "/opt/piper/voices/en_US-amy-medium.onnx")
      }
      env {
        name  = "WAV2LIP_CHECKPOINT"
        value = lookup(var.app_env, "WAV2LIP_CHECKPOINT", "/models/wav2lip/wav2lip_gan.pth")
      }

      # Secrets -> env
      env {
        name        = "FAL_API_KEY"
        secret_name = "fal-api-key"
      }
      env {
        name        = "D_ID_API_KEY"
        secret_name = "did-api-key"
      }
      dynamic "env" {
        for_each = try(var.sadtalker_base, null) != null && var.sadtalker_base != "" ? [1] : []
        content {
          name        = "SADTALKER_BASE"
          secret_name = "sadtalker-base"
        }
      }

      # Mounts (use `path` for ACA)
      dynamic "volume_mounts" {
        for_each = var.use_azure_files ? toset(["models", "voices", "outputs"]) : []
        content {
          name = volume_mounts.value
          path = lookup({
            models  = "/models",
            voices  = "/opt/piper/voices",
            outputs = "/app/outputs"
          }, volume_mounts.value, "/mnt/${volume_mounts.value}")
        }
      }
    }

    # Volumes bound to environment storages
    dynamic "volume" {
      for_each = var.use_azure_files ? {
        models  = azurerm_container_app_environment_storage.models[0].name
        voices  = azurerm_container_app_environment_storage.voices[0].name
        outputs = azurerm_container_app_environment_storage.outputs[0].name
      } : {}
      content {
        name         = volume.key
        storage_type = "AzureFile"
        storage_name = volume.value
      }
    }
  }

  depends_on = [time_sleep.after_build]
}

########################################
# Outputs
########################################
output "app_url" {
  value       = "https://${azurerm_container_app.app.latest_revision_fqdn}"
  description = "Public URL for the Container App."
}
