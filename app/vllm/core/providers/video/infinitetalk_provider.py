# app/vllm/core/providers/video/infinitetalk_provider.py
import os, time, requests
from .base import VideoProvider

class InfiniteTalkProvider(VideoProvider):
    """
    Cloud API provider.
    Requires:
      INFINITALK_API_KEY
      (optional) INFINITALK_BASE, default https://api.infinitetalk.net
      (optional) INFINITALK_CA_BUNDLE -> custom CA path for TLS verify
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
            r = requests.post(
                f"{self.base}/v1/talking-head",
                headers=self.headers, files=files, data=data,
                timeout=60, verify=_VERIFY
            )
        r.raise_for_status()
        js = r.json()
        job_id = js.get("id") or js.get("job_id")
        if not job_id:
            raise RuntimeError(f"InfiniteTalk: unexpected response: {js}")

        start = time.time()
        while True:
            s = requests.get(
                f"{self.base}/v1/talking-head/{job_id}",
                headers=self.headers, timeout=30, verify=_VERIFY
            )
            s.raise_for_status()
            st = s.json()
            status = st.get("status")
            if status in ("succeeded", "completed", "done"):
                video_url = st.get("video_url") or st.get("result", {}).get("video_url")
                if not video_url:
                    raise RuntimeError(f"InfiniteTalk: missing video URL: {st}")
                with requests.get(video_url, timeout=180, verify=_VERIFY, stream=True) as resp:
                    resp.raise_for_status()
                    with open(out_mp4_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                return out_mp4_path
            if status in ("failed", "error"):
                raise RuntimeError(st.get("error", "InfiniteTalk job failed."))
            if time.time() - start > self.timeout_s:
                raise TimeoutError("InfiniteTalk timed out.")
            time.sleep(2)


class InfiniteTalkLocalProvider:
    """
    Local sidecar provider (your FastAPI GPU container).
    Env:
      INFINITALK_URL (default http://infinitetalk:8000)
      INFINITALK_API_KEY (optional x-api-key)
    """
    def generate(self, face_image_path, audio_wav_path, out_mp4_path, fps=25, size=512, **kwargs):
        base = os.getenv("INFINITALK_URL", "http://infinitetalk:8000").rstrip("/")
        api_key = os.getenv("INFINITALK_API_KEY", "")
        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)

        headers = {"x-api-key": api_key} if api_key else {}
        data = {"fps": str(int(fps)), "size": str(int(size))}

        with open(face_image_path, "rb") as fimg:
            files = {"image": ("face.png", fimg, "image/png")}
            if audio_wav_path:
                with open(audio_wav_path, "rb") as faud:
                    files["audio"] = ("audio.wav", faud, "audio/wav")
                    r = requests.post(f"{base}/generate", files=files, data=data, headers=headers, timeout=3600)
            else:
                r = requests.post(f"{base}/generate", files=files, data=data, headers=headers, timeout=3600)

        r.raise_for_status()
        with open(out_mp4_path, "wb") as f:
            f.write(r.content)
        return out_mp4_path