project  = "vllmtes"
location = "uksouth"

dockerfile_path = "Dockerfile"
app_src_path    = "../"

image_name = "vllm"
image_tag  = "latest"

app_port = 8501

fal_api_key  = "19fff532-18a9-471b-b754-0b3f93855652:1a58841a03aa4c77486ed9acbe3214e2"
d_id_api_key = "ZWppdHVuZGUzQGdtYWlsLmNvbQ:Kg_E2A2C8K7tpZZaq9MDt"

sadtalker_base = "https://jamiu001-sadtalker.hf.space"

app_env = {
  PIPER_BIN          = "/usr/local/bin/piper"
  PIPER_VOICE        = "/opt/piper/voices/en_US-amy-medium.onnx"
  WAV2LIP_CHECKPOINT = "/models/wav2lip/wav2lip_gan.pth"

  FAL_VEO3_AR       = "16:9"
  FAL_VEO3_DURATION = "8s"
  FAL_VEO3_RES      = "720p"
  FAL_VEO3_AUDIO    = "true"
}