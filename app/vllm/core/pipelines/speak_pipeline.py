import os, io
from typing import Dict
from PIL import Image
from vllm.core.providers.tts.base import TTSProvider
from vllm.core.providers.video.base import VideoProvider
from vllm.core.utils.io import temp_workdir


class SpeakPipeline:
    def __init__(self, tts: TTSProvider, video: VideoProvider):
        self.tts = tts
        self.video = video

    def invoke(self, inputs: Dict) -> Dict:
        """
        Returns in-memory bytes so Streamlit can render immediately,
        avoiding 'file not found' after the temp dir is cleaned up.
        """
        image_file = inputs["image_file"]  # streamlit UploadedFile
        text = inputs["text"]
        fps = int(inputs.get("fps", 25))
        size = int(inputs.get("size", 512))

        with temp_workdir("avatar_") as work:
            face_path = os.path.join(work, "face.png")
            audio_path = os.path.join(work, "speech.wav")
            video_path = os.path.join(work, "result.mp4")

            # Save the uploaded image to disk
            img = Image.open(io.BytesIO(image_file.read())).convert("RGB")
            img.save(face_path)

            # TTS -> WAV on disk
            self.tts.synthesize(text, audio_path)

            # Video -> MP4 on disk
            self.video.generate(face_path, audio_path, video_path, fps=fps, size=size)

            # Read bytes BEFORE the temp dir is cleaned up
            with open(audio_path, "rb") as fa:
                audio_bytes = fa.read()
            with open(video_path, "rb") as fv:
                video_bytes = fv.read()

            # Also return convenient default filenames
            return {
                "audio_bytes": audio_bytes,
                "video_bytes": video_bytes,
                "audio_name": "speech.wav",
                "video_name": "result.mp4",
            }