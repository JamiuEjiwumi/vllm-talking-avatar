import os, subprocess, shlex
from vllm.core.providers.video.base import VideoProvider


class InfiniteTalkProvider(VideoProvider):
    def __init__(self, checkpoint_path: str | None = None):
        self.repo_dir = "/app/InfiniteTalk"
        self.checkpoint = checkpoint_path or os.getenv(
            "INFINITETALK_CHECKPOINT", 
            os.path.join(self.repo_dir, "checkpoints", "infinite_talk.pth")
        )

    def generate(self, face_image_path: str, audio_wav_path: str,
                 out_mp4_path: str, fps: int = 25, size: int = 512) -> str:
        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)
        cmd = (
            f"python {shlex.quote(self.repo_dir)}/inference.py "
            f"--face {shlex.quote(face_image_path)} "
            f"--audio {shlex.quote(audio_wav_path)} "
            f"--outfile {shlex.quote(out_mp4_path)} "
            f"--checkpoint_path {shlex.quote(self.checkpoint)} "
            f"--fps {int(fps)} --resize_factor {max(1, int(512/size))}"
        )
        subprocess.run(cmd, cwd=self.repo_dir, shell=True, check=True)
        return out_mp4_path