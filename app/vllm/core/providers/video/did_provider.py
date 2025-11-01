# app/vllm/core/providers/video/did_provider.py
import os
import re
import time
import base64
import requests
from typing import Optional
from .base import VideoProvider

DID_BASE = "https://api.d-id.com"
POLL_INTERVAL_SEC = 2
JOB_TIMEOUT_SEC = 600  # 10 minutes


class DIDProvider(VideoProvider):
    """
    D-ID provider: local image + D-ID voice (text) -> talking head MP4.

    Flow:
      1) POST /images (multipart) with local face image -> { id, url (S3) }
      2) POST /talks with source_url = S3 url, script = { type: text, input, provider }
      3) Poll GET /talks/{id} until status == "done", then download result_url

    NOTE: Some D-ID plans do NOT support script.type='ssml'. This provider always
    sends 'text'. If DID_USE_SSML=1, we strip SSML tags to safe text as a fallback.
    """
    capabilities = {"lip_sync"}

    def __init__(self):
        api_key = os.getenv("D_ID_API_KEY")
        if not api_key:
            raise RuntimeError("D_ID_API_KEY is required (set it in your environment).")

        # Basic auth: username = API key, password = empty
        auth = base64.b64encode((api_key + ":").encode()).decode()

        self.sess = requests.Session()
        self.sess.headers.update({
            "Authorization": f"Basic {auth}",
            # Don't set Content-Type globally; requests sets it for multipart/json
        })

        # Voice config
        self.voice_id = os.getenv("DID_VOICE", "en-US-GuyNeural")
        self.voice_provider = os.getenv("DID_VOICE_PROVIDER", "microsoft")

    # ------------------------- Internal helpers -------------------------

    def _upload_image(self, face_image_path: str) -> tuple[str, str]:
        """Upload local file to D-ID /images. Returns (image_id, s3_url)."""
        with open(face_image_path, "rb") as f:
            files = {"image": (os.path.basename(face_image_path), f, "application/octet-stream")}
            r = self.sess.post(f"{DID_BASE}/images", files=files, timeout=60)

        if not r.ok:
            raise RuntimeError(f"D-ID /images failed [{r.status_code}]: {r.text}")

        data = r.json()
        img_id = data.get("id")
        s3_url = data.get("url")
        if not img_id or not s3_url:
            raise RuntimeError(f"D-ID /images missing fields: {data}")
        return img_id, s3_url

    def _strip_ssml(self, text: str) -> str:
        """
        Fallback: remove SSML tags and collapse whitespace so we can send plain text.
        Keeps punctuation to preserve some prosody effects.
        """
        # Remove XML/SSML tags like <speak>...</speak>, <prosody ...>, <break .../>, etc.
        no_tags = re.sub(r"<[^>]+>", " ", text)
        # Unescape basic entities if present (minimal)
        no_tags = no_tags.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        # Collapse whitespace
        return re.sub(r"\s+", " ", no_tags).strip()

    def _create_talk(self, source_url: str, text: str) -> str:
        """
        Create a D-ID talk using uploaded image S3 URL and TEXT script.
        D-ID plan here rejects 'ssml', so we always send 'text'.
        If DID_USE_SSML=1, we strip SSML tags first.
        """
        use_ssml = os.getenv("DID_USE_SSML", "0") == "1"
        driver_url = os.getenv("DID_DRIVER_URL")  # optional public MP4 to drive motion

        input_text = self._strip_ssml(text) if use_ssml else text

        script = {
            "type": "text",          # <-- force text (no ssml)
            "input": input_text,
            "provider": {
                "type": self.voice_provider,
                "voice_id": self.voice_id
            }
        }

        payload = {
            "source_url": source_url,
            "script": script,
            "config": {
                "stitch": True
            }
        }
        if driver_url:
            payload["driver_url"] = driver_url

        r = self.sess.post(
            f"{DID_BASE}/talks",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        if not r.ok:
            raise RuntimeError(f"D-ID /talks failed [{r.status_code}]: {r.text}")

        talk_id = r.json().get("id")
        if not talk_id:
            raise RuntimeError(f"D-ID /talks returned no id: {r.text}")
        return talk_id

    def _wait_and_download(self, talk_id: str, out_mp4_path: str) -> str:
        """Poll /talks/{id} until done; download result_url to out_mp4_path."""
        start = time.time()
        while True:
            g = self.sess.get(f"{DID_BASE}/talks/{talk_id}", timeout=30)
            if not g.ok:
                raise RuntimeError(f"D-ID /talks/{talk_id} failed [{g.status_code}]: {g.text}")

            data = g.json()
            status = (data.get("status") or "").lower()

            if status == "done":
                result_url = data.get("result_url") or (data.get("result") or {}).get("url")
                if not result_url:
                    raise RuntimeError(f"D-ID returned no result_url: {data}")

                vid = requests.get(result_url, timeout=300)
                vid.raise_for_status()
                os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)
                with open(out_mp4_path, "wb") as f:
                    f.write(vid.content)
                return out_mp4_path

            if status in ("error", "failed"):
                raise RuntimeError(f"D-ID talk failed: {data}")

            if time.time() - start > JOB_TIMEOUT_SEC:
                raise RuntimeError(f"D-ID timed out after {JOB_TIMEOUT_SEC}s (talk_id={talk_id})")

            time.sleep(POLL_INTERVAL_SEC)

    # ------------------------- Public API -------------------------

    def generate(
        self,
        face_image_path: str,
        audio_wav_path: Optional[str],  # ignored in text mode
        out_mp4_path: str,
        fps: int = 25,                  # not used by D-ID (interface parity)
        size: int = 512,                # not used by D-ID (interface parity)
    ) -> str:
        if not os.path.exists(face_image_path):
            raise FileNotFoundError(face_image_path)

        # Text to speak (priority: DID_TEXT > FAL_TEXT > default)
        text = os.getenv("DID_TEXT") or os.getenv("FAL_TEXT") or "Hello from D-ID."

        # 1) Upload image -> S3 URL
        _, s3_url = self._upload_image(face_image_path)

        # 2) Create talk (text only; SSML will be stripped if present)
        talk_id = self._create_talk(s3_url, text)

        # 3) Poll & download
        return self._wait_and_download(talk_id, out_mp4_path)
