# app/vllm/core/providers/video/sadtalker_provider.py
import os
import time
import json
import base64
import logging
import requests
from typing import Optional

from .base import VideoProvider

log = logging.getLogger("sadtalker")

DEFAULT_BASE = "https://vinthony-sadtalker.hf.space"  # override via SADTALKER_BASE

def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def _b64(prefix: str, data: bytes) -> str:
    return prefix + base64.b64encode(data).decode()

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default

def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")

class SadTalkerProvider(VideoProvider):
    """
    SadTalker over Hugging Face Spaces, with:
      - Warm-up GET
      - Multipart /run/predict attempt
      - Multiple /api/predict JSON layouts (gradio variants)
      - HTML detection (sleep/redirect)
      - Retries + backoff
      - Clear, verbose error surfacing
    Tunables (env):
      SADTALKER_BASE, SADTALKER_TIMEOUT, SADTALKER_POSE_SCALE, SADTALKER_EXPRESSION_SCALE,
      SADTALKER_STILL_MODE, SADTALKER_PREPROCESS, SADTALKER_ENHANCER
    """
    capabilities = {"lip_sync", "head_movement", "eye_blink"}

    def __init__(self):
        base = os.getenv("SADTALKER_BASE", DEFAULT_BASE).rstrip("/")
        self.base = base
        self.endpoint_run = f"{self.base}/run/predict"
        self.endpoint_api = f"{self.base}/api/predict"
        self.timeout = int(os.getenv("SADTALKER_TIMEOUT", "240"))

        # Motion/quality knobs
        self.pose_scale = _env_float("SADTALKER_POSE_SCALE", 1.0)
        self.expression_scale = _env_float("SADTALKER_EXPRESSION_SCALE", 1.0)
        self.still_mode = _env_bool("SADTALKER_STILL_MODE", False)
        self.preprocess = os.getenv("SADTALKER_PREPROCESS", "full")  # "full"|"crop"
        self.enhancer = os.getenv("SADTALKER_ENHANCER", "gfpgan")   # "gfpgan"|"none"

        self.session = requests.Session()

    # ---------------- helpers ----------------

    def _warmup(self):
        try:
            log.info("[sadtalker] warmup GET %s", self.base)
            self.session.get(self.base, timeout=10)
        except Exception as e:
            log.debug("[sadtalker] warmup ignored: %s", e)

    def _looks_like_html(self, text: str) -> bool:
        if not text:
            return False
        s = text.strip().lower()
        return s.startswith("<!doctype html") or s.startswith("<html")

    def _backoff_attempts(self):
        # (try_index, sleep_seconds)
        for i in range(4):
            yield i + 1, (2 ** i) - 1 if i > 0 else 0  # 0s, 1s, 3s, 7s

    def _parse_result_url(self, obj) -> Optional[str]:
        try:
            if isinstance(obj, dict):
                d = obj.get("data")
                if isinstance(d, list) and d:
                    first = d[0]
                    if isinstance(first, dict) and "url" in first and str(first["url"]).startswith("http"):
                        return first["url"]
                    if isinstance(first, str) and first.startswith("http"):
                        return first
                # flat dict with url
                if "url" in obj and str(obj["url"]).startswith("http"):
                    return obj["url"]
        except Exception:
            pass
        return None

    def _download_to(self, url: str, out_path: str) -> str:
        log.info("[sadtalker] downloading %s", url)
        r = self.session.get(url, timeout=max(self.timeout, 300))
        r.raise_for_status()
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(r.content)
        log.info("[sadtalker] saved: %s", out_path)
        return out_path

    # ----- request variants -----

    def _post_multipart(self, img_bytes: bytes, wav_bytes: bytes) -> requests.Response:
        files = {
            "image": ("face.png", img_bytes, "image/png"),
            "audio": ("audio.wav", wav_bytes, "audio/wav"),
        }
        data = {
            "preprocess": self.preprocess,
            "enhancer": self.enhancer,
            "still": "true" if self.still_mode else "false",
            "pose_scale": str(self.pose_scale),
            "expression_scale": str(self.expression_scale),
        }
        return self.session.post(self.endpoint_run, files=files, data=data, timeout=self.timeout)

    def _post_gradio_layouts(self, img_bytes: bytes, wav_bytes: bytes):
        """
        Yield possible JSON payloads for /api/predict. Different Spaces wire
        components differently; we try a few common layouts.
        """
        img_b64 = _b64("data:image/png;base64,", img_bytes)
        wav_b64 = _b64("data:audio/wav;base64,", wav_bytes)

        # Layout A: [image, audio, preprocess, enhancer, still, pose_scale, expression_scale]
        yield {
            "data": [img_b64, wav_b64, self.preprocess, self.enhancer,
                     self.still_mode, self.pose_scale, self.expression_scale]
        }

        # Layout B: [image, audio, still, pose_scale, expression_scale, preprocess, enhancer]
        yield {
            "data": [img_b64, wav_b64, self.still_mode,
                     self.pose_scale, self.expression_scale, self.preprocess, self.enhancer]
        }

        # Layout C: named dict (some Spaces accept dict-like data)
        yield {
            "data": [{
                "image": img_b64,
                "audio": wav_b64,
                "preprocess": self.preprocess,
                "enhancer": self.enhancer,
                "still": self.still_mode,
                "pose_scale": self.pose_scale,
                "expression_scale": self.expression_scale
            }]
        }

    # ---------------- public API ----------------

    def generate(
        self,
        face_image_path: str,
        audio_wav_path: Optional[str],
        out_mp4_path: str,
        fps: int = 25,
        size: int = 512,
    ) -> str:
        log.info("[sadtalker] generating → img=%s audio=%s", face_image_path, audio_wav_path)

        if not os.path.exists(face_image_path):
            raise FileNotFoundError(f"Face image not found: {face_image_path}")
        if not audio_wav_path or not os.path.exists(audio_wav_path):
            raise FileNotFoundError(f"Audio not found: {audio_wav_path}")

        img_bytes = _read_bytes(face_image_path)
        wav_bytes = _read_bytes(audio_wav_path)

        self._warmup()

        # Phase 1: multipart /run/predict with retries
        last_detail = None
        for attempt, sleep_s in self._backoff_attempts():
            if sleep_s:
                time.sleep(sleep_s)
            try:
                log.info("[sadtalker] /run/predict attempt %d -> %s", attempt, self.endpoint_run)
                resp = self._post_multipart(img_bytes, wav_bytes)
                txt = (resp.text or "")[:2048]
                if self._looks_like_html(txt):
                    last_detail = f"HTML from /run/predict (sleep/redirect). First bytes:\n{txt}"
                    log.warning("[sadtalker] %s", last_detail)
                    break  # go to JSON phase
                if 500 <= resp.status_code < 600:
                    last_detail = f"5xx on /run/predict [{resp.status_code}]: {txt}"
                    log.warning("[sadtalker] %s", last_detail)
                    continue
                # 2xx or 4xx → try to parse JSON
                try:
                    obj = resp.json()
                except Exception:
                    last_detail = f"Non-JSON from /run/predict [{resp.status_code}]: {txt}"
                    log.warning("[sadtalker] %s", last_detail)
                    break  # go to JSON phase
                url = self._parse_result_url(obj)
                if url:
                    return self._download_to(url, out_mp4_path)
                last_detail = f"No URL in /run/predict JSON: {json.dumps(obj)[:2048]}"
                log.warning("[sadtalker] %s", last_detail)
                break  # go to JSON phase
            except Exception as e:
                last_detail = f"Exception on /run/predict: {e}"
                log.warning("[sadtalker] %s", last_detail)

        # Phase 2: /api/predict JSON layouts with retries
        headers = {"Content-Type": "application/json"}
        for payload in self._post_gradio_layouts(img_bytes, wav_bytes):
            for attempt, sleep_s in self._backoff_attempts():
                if sleep_s:
                    time.sleep(sleep_s)
                try:
                    log.info("[sadtalker] /api/predict attempt %d with layout %s",
                             attempt, list(payload.keys()))
                    resp = self.session.post(self.endpoint_api, json=payload,
                                             headers=headers, timeout=self.timeout)
                    txt = (resp.text or "")[:2048]
                    if self._looks_like_html(txt):
                        last_detail = f"HTML from /api/predict (UI, not API). First bytes:\n{txt}"
                        log.warning("[sadtalker] %s", last_detail)
                        continue
                    if 500 <= resp.status_code < 600:
                        last_detail = f"5xx on /api/predict [{resp.status_code}]: {txt}"
                        log.warning("[sadtalker] %s", last_detail)
                        continue
                    # Parse JSON
                    try:
                        obj = resp.json()
                    except Exception:
                        last_detail = f"Non-JSON from /api/predict [{resp.status_code}]: {txt}"
                        log.warning("[sadtalker] %s", last_detail)
                        continue
                    url = self._parse_result_url(obj)
                    if url:
                        return self._download_to(url, out_mp4_path)
                    last_detail = f"No URL in /api/predict JSON: {json.dumps(obj)[:2048]}"
                    log.warning("[sadtalker] %s", last_detail)
                except Exception as e:
                    last_detail = f"Exception on /api/predict: {e}"
                    log.warning("[sadtalker] %s", last_detail)

        # If we reached here, everything failed. Show the best detail we captured.
        raise RuntimeError(f"SadTalker API failed: {last_detail or 'no detail captured'}")
