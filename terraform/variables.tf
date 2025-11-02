variable "project" {
  type        = string
  description = "Short project name (used to name resources)."
  default     = "vllm"
}

variable "location" {
  type        = string
  description = "Azure region."
  default     = "westeurope"
}

variable "image_name" {
  type    = string
  default = "vllm"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "app_port" {
  description = "Container port the app listens on."
  type        = number
  default     = 8080
}

variable "use_azure_files" {
  description = "Whether to mount Azure Files for models/voices/outputs."
  type        = bool
  default     = true
}

variable "app_env" {
  description = "Non-secret environment variables for the container."
  type        = map(string)
  default = {
    STREAMLIT_SERVER_HEADLESS          = "true"
    STREAMLIT_SERVER_ADDRESS           = "0.0.0.0"
    STREAMLIT_BROWSER_GATHERUSAGESTATS = "false"
    STREAMLIT_SERVER_FILEWATCHER_TYPE  = "none"

    ORT_LOG_SEVERITY_LEVEL = "3"

    FAL_TIMEOUT            = "1800"
    FAL_REQ_TIMEOUT        = "45"
    FAL_POLL_EVERY         = "2.0"
    FAL_RESPONSE_GRACE     = "60"
    FAL_CONC_BACKOFF_S     = "5"
    FAL_CONC_BACKOFF_MAX   = "60"
    FAL_MAX_SUBMIT_RETRIES = "40"

    FAL_INF_ENDPOINT  = "fal-ai/infinitalk/single-text"
    FAL_QUEUE_BASE    = "https://queue.fal.run"
    FAL_VEO3_ENDPOINT = "fal-ai/veo3"

    SADTALKER_POSE_SCALE       = "1.2"
    SADTALKER_EXPRESSION_SCALE = "1.3"
    SADTALKER_STILL_MODE       = "false"
    SADTALKER_PREPROCESS       = "full"
    SADTALKER_ENHANCER         = "gfpgan"
    SADTALKER_TIMEOUT          = "300"

    PIPER_BIN          = "/usr/local/bin/piper"
    PIPER_VOICE        = "/opt/piper/voices/en_US-amy-medium.onnx"
    WAV2LIP_CHECKPOINT = "/models/wav2lip/wav2lip_gan.pth"
  }
}

variable "fal_api_key" {
  description = "FAL API key."
  type        = string
  sensitive   = true
}

variable "d_id_api_key" {
  description = "D-ID API key (email:token)."
  type        = string
  sensitive   = true
}

variable "sadtalker_base" {
  description = "Your Hugging Face SadTalker Space URL (optional)."
  type        = string
  default     = ""
}

variable "app_src_path" {
  description = "Path to Docker build context."
  type        = string
  default     = "./"
}

variable "dockerfile_path" {
  description = "Path to Dockerfile relative to repo root."
  type        = string
  default     = "Dockerfile"
}
