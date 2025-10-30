from abc import ABC, abstractmethod

class VideoProvider(ABC):
    @abstractmethod
    def generate(self, face_image_path: str, audio_wav_path: str, out_mp4_path: str, fps: int = 25, size: int = 512) -> str:
        raise NotImplementedError
