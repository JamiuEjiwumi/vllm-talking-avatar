project            = "vllmtes"
location           = "northeurope"
image_name         = "vllm"
image_tag          = "latest"
container_port     = 8501
cpu                = 4
memory_gb          = 16
gpu_count          = 1
# use_spot_instances = false
env_vars = {
  PIPER_BIN               = "/usr/local/bin/piper"
  PIPER_VOICE             = "/mnt/voices/en_US-amy-medium.onnx"
  WAV2LIP_CHECKPOINT      = "/mnt/models/wav2lip/wav2lip_gan.pth"
  INFINITETALK_CHECKPOINT = "/mnt/models/infinitetalk"
}
dockerfile_path   = "Dockerfile"
app_src_path      = "./"