import os, time, json, requests
from .base import VideoProvider

class RunpodInfiniteTalkProvider(VideoProvider):
    """
    Uses RunPod Public Endpoint for InfiniteTalk.
    Env:
      RUNPOD_API_KEY   (required)
      RUNPOD_ENDPOINT  (optional, default 'InfiniteTalk')  # from your screenshot
      RUNPOD_BASE      (optional, default 'https://api.runpod.ai')
      RUNPOD_POLL_EVERY (optional, default '2')
      RUNPOD_TIMEOUT_S (optional, default '600')
    """
    capabilities = {"lip_sync"}

    def __init__(self):
        self.api_key = os.getenv("RUNPOD_API_KEY")
        if not self.api_key:
            raise RuntimeError("RUNPOD_API_KEY is required.")
        self.endpoint = os.getenv("RUNPOD_ENDPOINT", "InfiniteTalk").strip("/")
        self.base = os.getenv("RUNPOD_BASE", "https://api.runpod.ai").rstrip("/")
        self.poll = float(os.getenv("RUNPOD_POLL_EVERY", "2"))
        self.timeout = int(os.getenv("RUNPOD_TIMEOUT_S", "600"))
        self.h = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _submit(self, payload):
        url = f"{self.base}/v2/{self.endpoint}/run"
        r = requests.post(url, headers=self.h, data=json.dumps(payload), timeout=60)
        r.raise_for_status()
        j = r.json()
        return j.get("id") or j.get("requestId")

    def _poll(self, req_id):
        url = f"{self.base}/v2/{self.endpoint}/status/{req_id}"
        start = time.time()
        while True:
            r = requests.get(url, headers=self.h, timeout=30)
            r.raise_for_status()
            j = r.json()
            s = j.get("status")
            if s in ("COMPLETED", "COMPLETED_WITH_WARNINGS", "SUCCEEDED"):
                # Most RunPod templates put the URL in output.video_url
                out = j.get("output") or {}
                return out.get("video_url") or out.get("url") or out
            if s in ("FAILED", "ERROR", "CANCELLED"):
                raise RuntimeError(f"RunPod job failed: {j}")
            if time.time() - start > self.timeout:
                raise TimeoutError("RunPod job timed out.")
            time.sleep(self.poll)

    def generate(self, face_image_path, audio_wav_path, out_mp4_path, fps=25, size=512, **kwargs):
        # This endpoint expects **URLs**, not raw files.
        image_url = os.getenv("RUNPOD_IMAGE_URL")   # quick testing lever
        audio_url = os.getenv("RUNPOD_AUDIO_URL")   # quick testing lever
        if not (image_url and audio_url):
            raise RuntimeError(
                "RunPod InfiniteTalk expects URL inputs. Set RUNPOD_IMAGE_URL and RUNPOD_AUDIO_URL "
                "to public HTTPS URLs (or add a small upload step to blob storage)."
            )

        payload = {
            "input": {
                "prompt": kwargs.get("prompt", "lip sync"),
                "image": image_url,
                "audio": audio_url,
                "fps": fps,
                "size": size,
                "enable_safety_checker": True
            }
        }
        req_id = self._submit(payload)
        video_url = self._poll(req_id)

        # stream download
        with requests.get(video_url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)
            with open(out_mp4_path, "wb") as f:
                for chunk in resp.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return out_mp4_path
