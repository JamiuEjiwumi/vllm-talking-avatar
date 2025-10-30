from abc import ABC, abstractmethod
from typing import Optional

class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, out_wav_path: str, voice: Optional[str] = None) -> str:
        """Generate speech to out_wav_path; return the path."""
        raise NotImplementedError
