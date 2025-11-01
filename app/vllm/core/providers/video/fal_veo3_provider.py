# app/vllm/core/providers/video/fal_veo3_provider.py
import os, time, json, logging, requests
from typing import Optional
from .base import VideoProvider

log = logging.getLogger("fal_veo3")

class FalVeo3Provider(VideoProvider):
    """
    Text-to-video via FAL Veo3 (cinematic generation; not lip-sync).
    Env:
      FAL_API_KEY           required
      FAL_VEO3_ENDPOINT     default: "fal-ai/veo3"
      FAL_QUEUE_BASE        default: "https://queue.fal.run"
      FAL_TIMEOUT           default: 1800 (overall)
      FAL_REQ_TIMEOUT       default: 45
      FAL_POLL_EVERY        default: 2.0
      FAL_RESPONSE_GRACE    default: 60
      FAL_CONC_BACKOFF_S    default: 5
      FAL_CONC_BACKOFF_MAX  default: 60
      FAL_MAX_SUBMIT_RETRIES default: 30
    """

    capabilities = {"text_to_video"}

    def __init__(self):
        self.api_key = os.getenv("FAL_API_KEY") or os.getenv("FAL_KEY")
        if not self.api_key:
            raise RuntimeError("FAL_API_KEY (or FAL_KEY) is required for Veo3.")
        self.endpoint = os.getenv("FAL_VEO3_ENDPOINT", "fal-ai/veo3")
        self.queue_base = os.getenv("FAL_QUEUE_BASE", "https://queue.fal.run").rstrip("/")
        self.queue_url = f"{self.queue_base}/{self.endpoint}"

        self.timeout = int(os.getenv("FAL_TIMEOUT", "1800"))
        self.req_timeout = int(os.getenv("FAL_REQ_TIMEOUT", "45"))
        self.poll_every = float(os.getenv("FAL_POLL_EVERY", "2.0"))
        self.response_grace = int(os.getenv("FAL_RESPONSE_GRACE", "60"))
        self.conc_backoff_s = int(os.getenv("FAL_CONC_BACKOFF_S", "5"))
        self.conc_backoff_max = int(os.getenv("FAL_CONC_BACKOFF_MAX", "60"))
        self.max_submit_retries = int(os.getenv("FAL_MAX_SUBMIT_RETRIES", "30"))

        self.sess = requests.Session()
        self.sess.headers.update({"Authorization": f"Key {self.api_key}"})

    # ---------- helpers ----------
    def _submit_once(self, prompt: str, aspect_ratio: str, duration: str,
                     resolution: str, generate_audio: bool,
                     img_bytes: Optional[bytes]):
        args = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,     # e.g. "16:9", "9:16", "1:1"
            "duration": duration,             # e.g. "5s", "8s", "10s"
            "resolution": resolution,         # e.g. "720p", "1080p"
            "enhance_prompt": True,
            "auto_fix": True,
            "generate_audio": bool(generate_audio),
        }
        if img_bytes:
            files = {"image": ("init.png", img_bytes, "image/png")}
            data = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in args.items()}
            return self.sess.post(self.queue_url, data=data, files=files, timeout=self.req_timeout)
        else:
            return self.sess.post(self.queue_url, json=args, timeout=self.req_timeout)

    def _submit_with_backoff(self, *args, **kwargs):
        delay = self.conc_backoff_s
        for attempt in range(1, self.max_submit_retries + 1):
            r = None
            try:
                r = self._submit_once(*args, **kwargs)
                if r.status_code in (409, 429):  # concurrency/limits
                    msg = r.text.strip()[:200]
                    log.warning("[veo3] concurrency gate (attempt %d): %s", attempt, msg)
                    time.sleep(delay)
                    delay = min(delay * 2, self.conc_backoff_max)
                    continue
                r.raise_for_status()
                j = r.json()
                if not all(k in j for k in ("status_url", "response_url")):
                    raise RuntimeError(f"Unexpected submit payload: {j}")
                return j["status_url"], j["response_url"], j.get("logs_url")
            except Exception as e:
                if r is not None and 500 <= r.status_code < 600:
                    time.sleep(min(delay, 10)); continue
                if r is not None and 400 <= r.status_code < 500 and r.status_code not in (409, 429):
                    raise
                time.sleep(min(delay, 10))
        raise RuntimeError("Veo3 submit retries exhausted (concurrency or transient errors).")

    def _poll_status(self, status_url: str):
        start = time.time()
        while True:
            r = self.sess.get(status_url, timeout=self.req_timeout)
            if r.status_code >= 500:
                time.sleep(self.poll_every); continue
            if r.status_code not in (200, 202):
                r.raise_for_status()
            try:
                st = r.json()
            except Exception:
                st = {"status": "unknown", "raw": r.text}
            status = (st.get("status") or "").lower()
            if status in ("completed", "succeeded", "success", "done"):
                return st
            if status in ("failed", "error", "canceled", "cancelled"):
                raise RuntimeError(f"Veo3 job failed: {json.dumps(st)[:800]}")
            if time.time() - start > self.timeout:
                raise RuntimeError("Veo3 job timed out while waiting.")
            time.sleep(self.poll_every)

    def _wait_response_json(self, response_url: str):
        start = time.time()
        while True:
            try:
                r = self.sess.get(response_url, timeout=self.req_timeout)
                if r.status_code == 404:
                    raise RuntimeError("response not ready")
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if time.time() - start > self.response_grace:
                    raise
                time.sleep(1.5)

    def _extract_video_url(self, payload: dict) -> Optional[str]:
        if "video" in payload:
            v = payload["video"]
            if isinstance(v, dict) and "url" in v: return v["url"]
            if isinstance(v, str) and v.startswith("http"): return v
        if "output" in payload and isinstance(payload["output"], dict):
            for k in ("video", "video_url", "url"):
                val = payload["output"].get(k)
                if isinstance(val, str) and val.startswith("http"): return val
        if "result" in payload and isinstance(payload["result"], dict):
            for k in ("video", "video_url", "url"):
                val = payload["result"].get(k)
                if isinstance(val, str) and val.startswith("http"): return val
        if isinstance(payload.get("url"), str) and payload["url"].startswith("http"):
            return payload["url"]
        return None

    def _download(self, url: str, out_path: str):
        with self.sess.get(url, stream=True, timeout=max(self.req_timeout, 300)) as r:
            r.raise_for_status()
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk: f.write(chunk)
        return out_path

    # ---------- public ----------
    def generate(self, face_image_path: Optional[str], audio_wav_path: Optional[str],
                 out_mp4_path: str, fps: int = 25, size: int = 512) -> str:
        """
        For API parity with base interface. We ignore fps/size; use env or defaults below.
        Reads text prompt from env FAL_VEO3_PROMPT (or FAL_TEXT as a fallback).
        Optionally conditions on face_image_path as init image.
        """
        prompt = (os.getenv("FAL_VEO3_PROMPT") or os.getenv("FAL_TEXT") or "").strip()
        if not prompt:
            raise RuntimeError("Provide a text prompt via FAL_VEO3_PROMPT (or FAL_TEXT).")

        # knobs via env (optional)
        aspect_ratio  = os.getenv("FAL_VEO3_AR", "16:9")
        duration      = os.getenv("FAL_VEO3_DURATION", "8s")
        resolution    = os.getenv("FAL_VEO3_RES", "720p")
        generate_audio = os.getenv("FAL_VEO3_AUDIO", "true").lower() == "true"

        img_bytes = None
        if face_image_path and os.path.exists(face_image_path):
            with open(face_image_path, "rb") as f: img_bytes = f.read()

        status_url, response_url, _ = self._submit_with_backoff(
            prompt, aspect_ratio, duration, resolution, generate_audio, img_bytes
        )
        self._poll_status(status_url)
        payload = self._wait_response_json(response_url)

        video_url = self._extract_video_url(payload)
        if not video_url:
            raise RuntimeError(f"Veo3 response missing video url: {json.dumps(payload)[:800]}")
        return self._download(video_url, out_mp4_path)
