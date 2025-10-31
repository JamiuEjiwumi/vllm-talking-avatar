# app/vllm/core/providers/video/fal_infinitalk_provider.py
import os
import io
import time
import base64
import requests
from typing import Optional
from PIL import Image

# ✅ Only fal_client
import fal_client
from fal_client.client import FalClientError

from .base import VideoProvider

# Tuning knobs
MAX_IMG_SIZE = 512
SDK_TIMEOUT  = 45    # seconds per HTTP call to fal (keep short to avoid proxy timeouts)
RETRIES      = 3
BACKOFF      = 3     # seconds
DL_TIMEOUT   = 300   # final mp4 download


def _encode_image_jpeg_data_uri(path: str, max_edge: int = MAX_IMG_SIZE) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_edge, max_edge), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"


def _pick_video_url(obj: dict) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    # typical fal response shapes
    if isinstance(obj.get("video"), dict) and obj["video"].get("url"):
        return obj["video"]["url"]
    return obj.get("video_url") or obj.get("url")


class FalInfinitalkProvider(VideoProvider):
    """
    InfiniteTalk via fal_client.run() on '/single-text' (Fal does TTS).
    Env:
      FAL_KEY / FAL_API_KEY  : id:secret
      FAL_INF_ENDPOINT       : default 'fal-ai/infinitalk/single-text'
      FAL_TEXT               : text prompt (set by SpeakPipeline for single-text)
      FAL_VOICE              : e.g. 'Bill' (optional; default 'Bill')
    """
    capabilities = {"lip_sync"}

    def __init__(self):
        key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if not key:
            raise RuntimeError("FAL_KEY (or FAL_API_KEY) is required for fal.ai.")
        os.environ.setdefault("FAL_KEY", key)

        # Favor single-text to keep payloads small (no WAV upload)
        self.endpoint = os.getenv("FAL_INF_ENDPOINT", "fal-ai/infinitalk/single-text")

    def generate(
        self,
        face_image_path: str,
        audio_wav_path: Optional[str],
        out_mp4_path: str,
        fps: int = 25,
        size: int = 512,
    ) -> str:
        print("[fal_infinitalk] generate() start; endpoint =", self.endpoint, flush=True)
        self._ensure_exists(face_image_path, "face image")
        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)

        if not self.endpoint.endswith("/single-text"):
            raise RuntimeError(
                "This provider expects 'fal-ai/infinitalk/single-text'. "
                "Set FAL_INF_ENDPOINT='fal-ai/infinitalk/single-text'."
            )

        return self._run_single_text(face_image_path, out_mp4_path, fps, size)

    def _run_single_text(self, face_image_path: str, out_mp4_path: str, fps: int, size: int) -> str:
        text = os.getenv("FAL_TEXT") or "Hello from InfiniteTalk"
        words = text.split()
        if len(words) > 120:
            text = " ".join(words[:120])

        voice = os.getenv("FAL_VOICE", "Bill")  # default voice; override via env

        print("[fal_infinitalk] preparing image…", flush=True)
        try:
            img_url = fal_client.upload_file(face_image_path)  # short call to v3.fal.media
            print("[fal_infinitalk] image uploaded (url)", flush=True)
        except Exception as e:
            print(f"[fal_infinitalk] upload failed ({e}); using data URI", flush=True)
            try:
                img_url = fal_client.encode_file(face_image_path)
            except Exception:
                img_url = _encode_image_jpeg_data_uri(face_image_path)

        # Payload tolerant to schema variants:
        #  - some expect 'text_input', others 'prompt'
        #  - recent versions require 'voice'
        payload = {
            "image_url": img_url,
            "text_input": text,
            "prompt": text,
            "voice": voice,
            "fps": int(fps),
            "size": {"width": int(size), "height": int(size)},
        }

        last_err = None
        for attempt in range(1, RETRIES + 1):
            try:
                print(f"[fal_infinitalk] submitting (attempt {attempt}/{RETRIES})…", flush=True)
                res = fal_client.run(self.endpoint, arguments=payload, timeout=SDK_TIMEOUT)

                video_url = (
                    _pick_video_url(res)
                    or _pick_video_url(res.get("data", {}))
                    or _pick_video_url(res.get("result", {}))
                )
                if not video_url:
                    raise RuntimeError(f"fal.infinitalk returned no video URL: {res}")

                print("[fal_infinitalk] downloading:", video_url, flush=True)
                r = requests.get(video_url, timeout=DL_TIMEOUT)
                r.raise_for_status()
                with open(out_mp4_path, "wb") as f:
                    f.write(r.content)
                print("[fal_infinitalk] saved:", out_mp4_path, flush=True)
                return out_mp4_path

            except (FalClientError, requests.RequestException, RuntimeError) as e:
                msg = str(e)
                # If backend complains about fields, try a minimal alt schema once
                if attempt == 1 and ("prompt" in msg or "voice" in msg or "field required" in msg.lower()):
                    print("[fal_infinitalk] schema mismatch — retrying with minimal payload", flush=True)
                    payload = {"image_url": img_url, "prompt": text, "voice": voice}
                else:
                    last_err = e
                print(f"[fal_infinitalk] attempt {attempt} failed: {e}", flush=True)
                if attempt < RETRIES:
                    time.sleep(BACKOFF)
                else:
                    raise RuntimeError(f"fal.infinitalk failed after {RETRIES} attempts: {e}") from e

    def _ensure_exists(self, path: str, desc: str):
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"{desc} file not found: {path}")
