import os, subprocess
from .base import VideoProvider

class Wav2LipProvider(VideoProvider):
    capabilities = {"lip_sync"}  # <— add this

    def __init__(self, checkpoint_path: str | None = None):
        self.checkpoint = checkpoint_path or os.getenv("WAV2LIP_CHECKPOINT", "/models/wav2lip/wav2lip_gan.pth")
        self.repo_dir = "/app/Wav2Lip"

    def generate(self, face_image_path, audio_wav_path, out_mp4_path, fps: int = 25, size: int = 512) -> str:
        if not os.path.isfile(self.checkpoint):
            raise FileNotFoundError(f"Wav2Lip checkpoint not found: {self.checkpoint}")
        if not os.path.isfile(face_image_path):
            raise FileNotFoundError(f"Face image missing: {face_image_path}")
        if not os.path.isfile(audio_wav_path):
            raise FileNotFoundError(f"Audio missing: {audio_wav_path}")

        os.makedirs(os.path.dirname(out_mp4_path), exist_ok=True)

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{self.repo_dir}:{self.repo_dir}/face_detection:{env.get('PYTHONPATH','')}"
        env.setdefault("OMP_NUM_THREADS", "1")
        env.setdefault("MKL_NUM_THREADS", "1")

        resize_factor = max(1, int(512 / max(128, int(size))))

        cmd = [
            "python","-u","inference.py",
            "--checkpoint_path", self.checkpoint,
            "--face", face_image_path,
            "--audio", audio_wav_path,
            "--outfile", out_mp4_path,
            "--fps", str(int(fps)),
            "--resize_factor", str(resize_factor),
            "--face_det_batch_size","1",
            "--wav2lip_batch_size","16",
            "--pads","0","10","0","10",
        ]
        subprocess.run(cmd, cwd=self.repo_dir, env=env, check=True)
        return out_mp4_path