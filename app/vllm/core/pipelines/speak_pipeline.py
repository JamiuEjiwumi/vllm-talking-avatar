# app/vllm/core/pipelines/speak_pipeline.py
import os, io, subprocess
from typing import Dict
from PIL import Image
from vllm.core.providers.tts.base import TTSProvider
from vllm.core.providers.video.base import VideoProvider
from vllm.core.utils.io import temp_workdir


def _mux_audio(in_video: str, wav_path: str, out_video: str) -> str:
    cmd = [
        "ffmpeg", "-y",
        "-i", in_video,
        "-i", wav_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest", out_video
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_video


class SpeakPipeline:
    def __init__(self, tts: TTSProvider, video: VideoProvider):
        self.tts = tts
        self.video = video

    def invoke(self, inputs: Dict) -> Dict:
        image_file = inputs.get("image_file")
        text = inputs["text"]
        fps = int(inputs.get("fps", 25))
        size = int(inputs.get("size", 512))

        with temp_workdir("avatar_") as work:
            face_path = os.path.join(work, "face.png")
            audio_path = os.path.join(work, "speech.wav")
            video_path = os.path.join(work, "result.mp4")

            # Save uploaded image (if provided)
            if image_file is not None:
                img = Image.open(io.BytesIO(image_file.read())).convert("RGB")
                img.save(face_path)

            # Always synthesize TTS → WAV
            self.tts.synthesize(text, audio_path)

            # Pass text to FAL_TEXT for single-text mode
            if getattr(self.video, "endpoint", "").endswith("/single-text"):
                os.environ["FAL_TEXT"] = text

            # Branch by provider type
            caps = getattr(self.video, "capabilities", set())

            if "lip_sync" in caps:
                self.video.generate(face_path, audio_path, video_path, fps=fps, size=size)

            elif "text_to_video" in caps:
                ref_img = face_path if image_file is not None else None
                self.video.generate_from_text(text, video_path, ref_image_path=ref_img)
                try:
                    muxed = os.path.join(work, "muxed.mp4")
                    _mux_audio(video_path, audio_path, muxed)
                    video_path = muxed
                except subprocess.CalledProcessError as e:
                    print(f"[WARN] ffmpeg mux failed: {e}")

            else:
                raise RuntimeError("Unknown video provider capabilities.")

            # Read results before cleanup
            with open(audio_path, "rb") as fa:
                audio_bytes = fa.read()
            with open(video_path, "rb") as fv:
                video_bytes = fv.read()

            return {
                "audio_bytes": audio_bytes,
                "video_bytes": video_bytes,
                "audio_name": "speech.wav",
                "video_name": "result.mp4",
            }
