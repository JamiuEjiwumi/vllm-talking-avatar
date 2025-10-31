import os
import time
import requests
import fal_client
from .base import VideoProvider


class FalVeo3Provider(VideoProvider):
    """
    fal.ai Veo 3 text-to-video provider.

    Generates a realistic video directly from text prompts.
    Uses fal.ai/veo3 endpoint.

    Env:
      FAL_KEY - your fal.ai API key (required)
    """

    capabilities = {"text_to_video"}

    def __init__(self):
        self.key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
        if not self.key:
            raise RuntimeError("FAL_KEY or FAL_API_KEY must be set for Veo3 access.")
        os.environ.setdefault("FAL_KEY", self.key)
        self.endpoint = "fal-ai/veo3"

    def generate_from_text(
        self,
        text_prompt: str,
        out_mp4_path: str,
        ref_image_path: str | None = None,
        aspect_ratio: str = "16:9",
        duration: str = "8s",
        resolution: str = "720p",
        generate_audio: bool = True,
    ) -> str:
        """Generate a short video using the Veo 3 model."""
        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)

        # The fal client automatically handles long-running inference.
        print(f"[VEO3] Submitting job to {self.endpoint}…")
        start = time.time()

        result = fal_client.run(
            self.endpoint,
            arguments={
                "prompt": text_prompt,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "enhance_prompt": True,
                "auto_fix": True,
                "resolution": resolution,
                "generate_audio": generate_audio,
            },
            timeout=600,  # 10 mins max
        )

        elapsed = time.time() - start
        print(f"[VEO3] Job finished in {elapsed:.1f}s")

        # Extract video URL
        video_data = result.get("video")
        if not video_data or "url" not in video_data:
            raise RuntimeError(f"Unexpected result from {self.endpoint}: {result}")

        video_url = video_data["url"]
        print(f"[VEO3] Downloading from {video_url}")

        # Download video locally
        r = requests.get(video_url, timeout=300)
        r.raise_for_status()
        with open(out_mp4_path, "wb") as f:
            f.write(r.content)

        print(f"[VEO3] Saved video → {out_mp4_path}")
        return out_mp4_path
