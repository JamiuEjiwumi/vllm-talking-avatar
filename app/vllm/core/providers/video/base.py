# app/vllm/core/providers/video/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Set
import os

class VideoProvider(ABC):
    """
    Providers advertise capability via `capabilities`:
      - {"lip_sync"}       : needs face image + audio; produces a talking-head video
      - {"text_to_video"}  : needs a text prompt (+ optional ref image); produces a video

    All methods must write to `out_mp4_path` and return that absolute path.
    """

    capabilities: Set[str] = set()

    # ---------- Lip-sync path (e.g., Wav2Lip, InfiniteTalk) ----------
    @abstractmethod
    def generate(
        self,
        face_image_path: str,
        audio_wav_path: str,
        out_mp4_path: str,
        fps: int = 25,
        size: int = 512,
    ) -> str:
        raise NotImplementedError

    # ---------- Text→video path (e.g., Veo 3) ----------
    def generate_from_text(
        self,
        prompt_text: str,
        out_mp4_path: str,
        ref_image_path: Optional[str] = None,
        aspect: str = "16:9",
        duration_s: int = 8,
        quality: str = "1080p",
    ) -> str:
        raise NotImplementedError("This provider does not implement text_to_video.")

    # ---------- Helpers ----------
    @staticmethod
    def _ensure_exists(path: str, kind: str) -> None:
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"{kind} not found: {path}")