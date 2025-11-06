FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y git ffmpeg python3 python3-pip && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy upstream repo (submodule) and our API
COPY upstream /app/upstream
COPY api /app/api

# Python deps
RUN python3 -m pip install --upgrade pip \
 && if [ -f /app/upstream/requirements.txt ]; then pip install -r /app/upstream/requirements.txt; fi \
 && pip install -r /app/api/requirements.txt

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "api.app:APP", "--host", "0.0.0.0", "--port", "8000"]