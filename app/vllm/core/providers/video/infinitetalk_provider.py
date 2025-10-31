# app/vllm/core/providers/video/infinitetalk_provider.py
import os, time, requests
from .base import VideoProvider

_CA = os.getenv("REQUESTS_CA_BUNDLE")  # optional corporate CA

class InfiniteTalkProvider(VideoProvider):
    """
    Requires:
      INFINITALK_API_KEY
      (optional) INFINITALK_BASE, default https://api.infinitetalk.net
    """
    capabilities = {"lip_sync"}

    def __init__(self, timeout_s: int = 600):
        self.key = os.getenv("INFINITALK_API_KEY")
        if not self.key:
            raise RuntimeError("INFINITALK_API_KEY is required.")
        self.base = os.getenv("INFINITALK_BASE", "https://api.infinitetalk.net").rstrip("/")
        self.timeout_s = timeout_s
        self.headers = {"Authorization": f"Bearer {self.key}"}

    def generate(self, face_image_path, audio_wav_path, out_mp4_path, fps: int = 25, size: int = 512) -> str:
        self._ensure_exists(face_image_path, "face image")
        self._ensure_exists(audio_wav_path, "audio")
        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)

        with open(face_image_path, "rb") as fi, open(audio_wav_path, "rb") as ai:
            files = {
                "image": ("image.png", fi, "image/png"),
                "audio": ("tts.wav", ai, "audio/wav"),
            }
            data = {"fps": str(int(fps)), "size": str(int(size))}
            r = requests.post(f"{self.base}/v1/talking-head",
                              headers=self.headers, files=files, data=data,
                              timeout=60, verify=_CA or True)
        r.raise_for_status()
        js = r.json()
        job_id = js.get("id") or js.get("job_id")
        if not job_id:
            raise RuntimeError(f"InfiniteTalk: unexpected response: {js}")

        start = time.time()
        while True:
            s = requests.get(f"{self.base}/v1/talking-head/{job_id}",
                             headers=self.headers, timeout=30, verify=_CA or True)
            s.raise_for_status()
            st = s.json()
            status = st.get("status")
            if status in ("succeeded", "completed", "done"):
                video_url = st.get("video_url") or st.get("result", {}).get("video_url")
                if not video_url:
                    raise RuntimeError(f"InfiniteTalk: missing video URL: {st}")
                vb = requests.get(video_url, timeout=180, verify=_CA or True).content
                with open(out_mp4_path, "wb") as f:
                    f.write(vb)
                return out_mp4_path
            if status in ("failed", "error"):
                raise RuntimeError(st.get("error", "InfiniteTalk job failed."))
            if time.time() - start > self.timeout_s:
                raise TimeoutError("InfiniteTalk timed out.")
            time.sleep(2)