import pyttsx3, soundfile as sf, numpy as np, tempfile, os
from .base import TTSProvider

class PyttsxTTS(TTSProvider):
    def synthesize(self, text: str, out_wav_path: str, voice=None) -> str:
        engine = pyttsx3.init()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_name = tmp.name
        engine.save_to_file(text, tmp_name)
        engine.runAndWait()
        data, sr = sf.read(tmp_name, always_2d=False)
        if hasattr(data, "ndim") and data.ndim > 1:
            import numpy as _np
            data = _np.mean(data, axis=1)
        sf.write(out_wav_path, data, sr)
        os.unlink(tmp_name)
        return out_wav_path
