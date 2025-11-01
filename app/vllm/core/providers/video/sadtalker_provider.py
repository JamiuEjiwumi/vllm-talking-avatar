# app/vllm/core/providers/video/sadtalker_provider.py
import os
import requests
import time
from typing import Optional
from .base import VideoProvider

class SadTalkerProvider(VideoProvider):
    capabilities = {"lip_sync", "head_movement", "eye_blink"}

    def __init__(self):
        self.api_url = "https://vinthony-sadtalker.hf.space/run/predict"

    def generate(
        self,
        face_image_path: str,
        audio_wav_path: Optional[str],
        out_mp4_path: str,
        fps: int = 25,
        size: int = 512,
    ) -> str:
        print(f"[sadtalker] generating → {face_image_path}", flush=True)

        if not os.path.exists(face_image_path):
            raise FileNotFoundError(f"Face image not found: {face_image_path}")
        if not audio_wav_path or not os.path.exists(audio_wav_path):
            raise FileNotFoundError(f"Audio not found: {audio_wav_path}")

        with open(face_image_path, "rb") as f:
            face_bytes = f.read()
        with open(audio_wav_path, "rb") as f:
            audio_bytes = f.read()

        files = {
            "image": ("face.png", face_bytes, "image/png"),
            "audio": ("audio.wav", audio_bytes, "audio/wav"),
        }
        data = {
            "expression": "natural",
            "enhancer": "gfpgan",
            "preprocess": "full",
        }

        print("[sadtalker] submitting to HF Space...", flush=True)
        response = requests.post(self.api_url, files=files, data=data, timeout=180)
        response.raise_for_status()
        result = response.json()

        if "data" not in result or not result["data"]:
            raise RuntimeError("SadTalker API returned no data")

        video_url = result["data"][0]["url"]
        print(f"[sadtalker] downloading from {video_url}", flush=True)

        video_data = requests.get(video_url, timeout=300).content
        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)
        with open(out_mp4_path, "wb") as f:
            f.write(video_data)

        print(f"[sadtalker] saved: {out_mp4_path}", flush=True)
        return out_mp4_path