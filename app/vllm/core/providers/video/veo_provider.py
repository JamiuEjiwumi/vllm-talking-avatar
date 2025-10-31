import os, time, base64, requests
from .base import VideoProvider

_GEM_BASE = "https://generativelanguage.googleapis.com/v1beta"
_CA = os.getenv("REQUESTS_CA_BUNDLE")

class VeoProvider(VideoProvider):
    """
    Requires:
      GOOGLE_API_KEY
      (optional) VEO_MODEL, default 'veo-3.1'
    """
    capabilities = {"text_to_video"}

    def __init__(self):
        self.key = os.getenv("GOOGLE_API_KEY")
        if not self.key:
            raise RuntimeError("GOOGLE_API_KEY is required for Veo.")
        self.model = os.getenv("VEO_MODEL", "veo-3.1")

    def generate_from_text(
        self,
        prompt_text: str,
        out_mp4_path: str,
        ref_image_path: str | None = None,
        aspect: str = "16:9",
        duration_s: int = 8,
        quality: str = "1080p",
    ) -> str:
        if not prompt_text or not prompt_text.strip():
            raise ValueError("Veo requires non-empty prompt_text.")
        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)

        params = {"key": self.key}
        url = f"{_GEM_BASE}/models/{self.model}:generateVideo"
        body = {
            "prompt": {"text": prompt_text.strip()},
            "generationConfig": {
                "aspectRatio": aspect,
                "durationSeconds": int(duration_s),
                "quality": quality
            }
        }
        if ref_image_path:
            self._ensure_exists(ref_image_path, "reference image")
            img_b = open(ref_image_path, "rb").read()
            body["prompt"]["image"] = {
                "mimeType": "image/png",
                "data": base64.b64encode(img_b).decode("utf-8")
            }

        r = requests.post(url, params=params, json=body, timeout=60, verify=_CA or True)
        r.raise_for_status()
        op = r.json().get("operation")
        if not op:
            raise RuntimeError(f"Veo: unexpected response: {r.text}")

        op_url = f"{_GEM_BASE}/operations/{op}"
        while True:
            s = requests.get(op_url, params=params, timeout=30, verify=_CA or True)
            s.raise_for_status()
            js = s.json()
            if js.get("done"):
                resp = js.get("response", {})
                video_uri = ((resp.get("video") or {}).get("uri")
                             or resp.get("videoUri")
                             or resp.get("result", {}).get("uri"))
                if not video_uri:
                    raise RuntimeError(f"Veo: missing video URI: {js}")
                vb = requests.get(video_uri, timeout=300, verify=_CA or True).content
                with open(out_mp4_path, "wb") as f:
                    f.write(vb)
                return out_mp4_path
            time.sleep(2)
