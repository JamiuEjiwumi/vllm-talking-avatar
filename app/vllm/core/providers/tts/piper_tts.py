import os, subprocess, shlex, shutil
from typing import Optional
from .base import TTSProvider

class PiperTTS(TTSProvider):
    def __init__(self, piper_bin: Optional[str] = None, voice_path: Optional[str] = None):
        candidate = piper_bin or os.getenv("PIPER_BIN", "/opt/piper/piper")
        found = shutil.which("piper")
        if not (os.path.isfile(candidate) and os.access(candidate, os.X_OK)) and found:
            candidate = found
        self.piper_bin = candidate
        self.voice_path = voice_path or os.getenv("PIPER_VOICE", "/opt/piper/voices/en_US-amy-medium.onnx")

    def synthesize(self, text: str, out_wav_path: str, voice: Optional[str] = None) -> str:
        if not (os.path.isfile(self.piper_bin) and os.access(self.piper_bin, os.X_OK)):
            raise FileNotFoundError(f"Piper not found/executable: {self.piper_bin}")
        model = voice or self.voice_path
        if not os.path.isfile(model):
            raise FileNotFoundError(f"Piper voice missing: {model}")
        os.makedirs(os.path.dirname(out_wav_path), exist_ok=True)
        cmd = f"{shlex.quote(self.piper_bin)} -m {shlex.quote(model)} -f {shlex.quote(out_wav_path)}"
        subprocess.run(cmd, input=text.encode("utf-8"), shell=True, check=True)
        return out_wav_path
