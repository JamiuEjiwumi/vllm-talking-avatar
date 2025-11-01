# app/vllm/core/providers/video/fal_infinitalk_provider.py
import os
import io
import time
import base64
import requests
from typing import Optional
from PIL import Image

import fal_client

from .base import VideoProvider

MAX_IMG_SIZE = 512
RETRIES = 5
BACKOFF = 10  # Wait longer for free tier
DL_TIMEOUT = 300

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
    if isinstance(obj.get("video"), dict) and obj["video"].get("url"):
        return obj["video"]["url"]
    return obj.get("video_url") or obj.get("url")

class FalInfinitalkProvider(VideoProvider):
    capabilities = {"lip_sync"}

    def __init__(self):
        key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if not key:
            raise RuntimeError("FAL_KEY required")
        os.environ.setdefault("FAL_KEY", key)
        self.endpoint = os.getenv("FAL_INF_ENDPOINT", "fal-ai/infinitalk/single-text")

    def generate(self, face_image_path: str, audio_wav_path: Optional[str], out_mp4_path: str, fps: int = 25, size: int = 512) -> str:
        print(f"[fal_infinitalk] generate() → {face_image_path}", flush=True)
        if not os.path.exists(face_image_path):
            raise FileNotFoundError(f"face image not found: {face_image_path}")

        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)

        text = os.getenv("FAL_TEXT", "Hello")
        voice = os.getenv("FAL_VOICE", "Bill")

        # Upload image
        try:
            img_url = fal_client.upload_file(face_image_path)
            print("[fal_infinitalk] image uploaded (url)", flush=True)
        except Exception as e:
            print(f"[fal_infinitalk] upload failed ({e}); using data URI", flush=True)
            img_url = _encode_image_jpeg_data_uri(face_image_path)

        payload = {
            "image_url": img_url,
            "text_input": text,
            "prompt": text,
            "voice": voice,
            "fps": fps,
            "size": {"width": size, "height": size},
        }

        # WAIT FOR SLOT + RUN
        for attempt in range(1, RETRIES + 1):
            try:
                print(f"[fal_infinitalk] run attempt {attempt}/{RETRIES} — waiting for free slot...", flush=True)
                result = fal_client.run(self.endpoint, arguments=payload, timeout=180)

                video_url = _pick_video_url(result)
                if not video_url:
                    raise RuntimeError("No video URL in result")

                r = requests.get(video_url, timeout=DL_TIMEOUT)
                r.raise_for_status()
                with open(out_mp4_path, "wb") as f:
                    f.write(r.content)
                print(f"[fal_infinitalk] saved: {out_mp4_path}", flush=True)
                return out_mp4_path

            except Exception as e:
                if "concurrent" in str(e).lower() or "limit" in str(e).lower():
                    if attempt < RETRIES:
                        print(f"[fal_infinitalk] 429 — waiting {BACKOFF}s for free slot...", flush=True)
                        time.sleep(BACKOFF)
                    else:
                        raise RuntimeError("Fal.ai free tier: max 2 concurrent jobs. Wait 1-2 min or upgrade.")
                else:
                    raise RuntimeError(f"fal.infinitalk failed: {e}") from e