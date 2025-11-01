# app/vllm/core/providers/video/did_provider.py
import os
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
    D-ID video provider: local image + D-ID voice (text) -> talking head MP4.

    Flow:
      1) POST /images (multipart) with the local face image -> returns { id, url (S3) }
      2) POST /talks with source_url = <S3 url>, script = { type: text, input: ... }
      3) GET /talks/{id} until status == "done", then download result_url (pre-signed S3)
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
            # NOTE: Don't set Content-Type globally; requests will set it for multipart/json as needed
        })

        # Optional env overrides
        self.voice_id = os.getenv("DID_VOICE", "en-US-GuyNeural")
        # provider type can be "microsoft", "elevenlabs", etc., if enabled on your D-ID account
        self.voice_provider = os.getenv("DID_VOICE_PROVIDER", "microsoft")

    # ------------------------- Internal helpers -------------------------

    def _upload_image(self, face_image_path: str) -> tuple[str, str]:
        """
        Upload a local file to D-ID /images.
        Returns (image_id, s3_url). We will use s3_url for source_url.
        """
        with open(face_image_path, "rb") as f:
            files = {
                "image": (os.path.basename(face_image_path), f, "application/octet-stream")
            }
            r = self.sess.post(f"{DID_BASE}/images", files=files, timeout=60)

        if not r.ok:
            raise RuntimeError(f"D-ID /images failed [{r.status_code}]: {r.text}")

        data = r.json()
        img_id = data.get("id")
        s3_url = data.get("url")
        if not img_id or not s3_url:
            raise RuntimeError(f"D-ID /images missing fields: {data}")
        return img_id, s3_url

    def _create_talk(self, source_url: str, text: str) -> str:
        """
        Create a D-ID talk using the uploaded image's S3 URL and a text script.
        """
        payload = {
            "source_url": source_url,
            "script": {
                "type": "text",
                "input": text,
                "provider": {
                    "type": self.voice_provider,
                    "voice_id": self.voice_id
                }
            },
            "config": {
                # Enable stitching for smoother output; add options here if needed
                "stitch": True
            }
        }

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
        """
        Poll /talks/{id} until done, then download result_url to out_mp4_path.
        """
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
        audio_wav_path: Optional[str],  # ignored for D-ID text mode
        out_mp4_path: str,
        fps: int = 25,                  # unused by D-ID (kept for interface parity)
        size: int = 512,                # unused by D-ID (kept for interface parity)
    ) -> str:
        """
        Generate a talking video using D-ID voices (text mode).
        - face_image_path: local path to the face image (required)
        - audio_wav_path: ignored (D-ID speaks the text itself)
        - out_mp4_path: where to save the resulting MP4
        """
        if not os.path.exists(face_image_path):
            raise FileNotFoundError(face_image_path)

        # Text to speak (order of precedence)
        # 1) DID_TEXT  2) FAL_TEXT (your existing env)  3) default
        text = os.getenv("DID_TEXT") or os.getenv("FAL_TEXT") or "Hello from D-ID."

        # 1) Upload image -> get S3 URL
        _, s3_url = self._upload_image(face_image_path)

        # 2) Create talk with the S3 URL
        talk_id = self._create_talk(s3_url, text)

        # 3) Poll & download MP4
        return self._wait_and_download(talk_id, out_mp4_path)
