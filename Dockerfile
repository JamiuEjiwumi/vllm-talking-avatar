FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIPER_BIN=/usr/local/bin/piper \
    PIPER_VOICE=/opt/piper/voices/en_US-amy-medium.onnx \
    WAV2LIP_CHECKPOINT=/models/wav2lip/wav2lip_gan.pth \
    ORT_LOG_SEVERITY_LEVEL=1 \
    PYTHONPATH=/app:/usr/local/lib/python3.10/site-packages

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

RUN python -m pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip uninstall -y fal || true \
 && pip show fal-client

RUN git clone --depth 1 https://github.com/Rudrabha/Wav2Lip.git /app/Wav2Lip

COPY app/ /app/app/

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit","run","/app/app/streamlit_app.py","--server.port=8501","--server.address=0.0.0.0","--server.headless=true"]