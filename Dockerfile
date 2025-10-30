# FROM python:3.10-slim
# ENV DEBIAN_FRONTEND=noninteractive

# # system deps
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     ffmpeg git curl ca-certificates build-essential \
#  && rm -rf /var/lib/apt/lists/*

# # python deps (CPU)
# RUN pip install --no-cache-dir \
#     torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --extra-index-url https://download.pytorch.org/whl/cpu && \
#     pip install --no-cache-dir \
#     streamlit==1.38.0 langchain numpy==1.23.5 scipy==1.10.1 numba==0.56.4 \
#     librosa==0.9.2 pydub moviepy soundfile tqdm pyttsx3 python-dotenv \
#     piper-tts pillow imageio imageio-ffmpeg scikit-image

# # clone Wav2Lip (used by your provider)
# RUN git clone https://github.com/Rudrabha/Wav2Lip.git /app/Wav2Lip

# # python deps (CPU)
# RUN pip install --no-cache-dir \
#     torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --extra-index-url https://download.pytorch.org/whl/cpu && \
#     pip install --no-cache-dir \
#     streamlit==1.38.0 langchain numpy==1.23.5 scipy==1.10.1 numba==0.56.4 \
#     librosa==0.9.2 pydub moviepy soundfile tqdm pyttsx3 python-dotenv \
#     piper-tts pillow imageio imageio-ffmpeg scikit-image \
#     opencv-python-headless==4.10.0.84


# # runtime env
# ENV PIPER_BIN=/usr/local/bin/piper \
#     PIPER_VOICE=/opt/piper/voices/en_US-amy-medium.onnx \
#     WAV2LIP_CHECKPOINT=/models/wav2lip/wav2lip_gan.pth

# # app lives here; you will bind-mount ./app -> /app/app
# WORKDIR /app

# EXPOSE 8501
# # IMPORTANT: point to absolute path that matches your mount
# CMD ["streamlit","run","/app/app/streamlit_app.py","--server.port=8501","--server.address=0.0.0.0","--server.headless=true"]

FROM python:3.10-slim

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PIPER_BIN=/usr/local/bin/piper \
    PIPER_VOICE=/opt/piper/voices/en_US-amy-medium.onnx \
    WAV2LIP_CHECKPOINT=/models/wav2lip/wav2lip_gan.pth

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Clone Wav2Lip repository (shallow clone for smaller size)
RUN git clone --depth 1 https://github.com/Rudrabha/Wav2Lip.git /app/Wav2Lip

# Copy application code
COPY app/ /app/app/

# Create a non-root user for safer runtime
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose Streamlit default port
EXPOSE 8501

# Healthcheck (optional but recommended)
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run the Streamlit app
CMD ["streamlit", "run", "/app/app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]