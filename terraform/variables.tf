variable "project" {
  type        = string
  default     = "vllm"
  description = "Project name prefix (must be short to fit storage account naming limits)"
  validation {
    condition     = length(var.project) <= 20
    error_message = "Project name must be 20 characters or less to fit within storage account naming constraints."
  }
}

variable "location" {
  type    = string
  default = "westeurope"
}

# Image repo name (no registry) e.g., "vllm"
variable "image_name" {
  type    = string
  default = "vllm"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

# Container port (e.g., Streamlit)
variable "container_port" {
  type    = number
  default = 8501
}

# Container resources
variable "cpu" {
  type    = number
  default = 4
}

variable "memory_gb" {
  type    = number
  default = 16
}

variable "gpu_count" {
  type    = number
  default = 1
}

# Use spot instances for GPU node pool (cost savings for testing)
# variable "use_spot_instances" {
#   type    = bool
#   default = false
# }

# Environment variables expected by the app
variable "env_vars" {
  type = map(string)
  default = {
    PIPER_BIN               = "/usr/local/bin/piper"
    PIPER_VOICE             = "/mnt/voices/en_US-amy-medium.onnx"
    WAV2LIP_CHECKPOINT      = "/mnt/models/wav2lip/wav2lip_gan.pth"
    INFINITETALK_CHECKPOINT = "/mnt/models/infinitetalk"
  }
}

variable "dockerfile_path" {
  type      = string
  sensitive = true
}

variable "app_src_path" {
  description = "Path to Docker build context for the API"
  type        = string
}